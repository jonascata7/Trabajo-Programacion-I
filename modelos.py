"""
modelos.py - Capa de modelo (POO) del sistema de rutinas de entrenamiento.

Jerarquías:
  Usuario (abstracta) -> Entrenador, Alumno            (herencia + polimorfismo)
  Serie   (abstracta) -> SerieNormal, SerieEspecial    (herencia + polimorfismo)
  Rutina -> Dia -> Bloque -> Serie                     (composición)

Todas las validaciones viven en los setters/constructores: si un objeto
existe, sus datos son válidos. Los errores se informan con ValidacionError
(subclase de ValueError), que las rutas de Flask capturan y devuelven como 400.
"""
import re
from abc import ABC, abstractmethod

from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------- constantes
MIN_DIAS, MAX_DIAS = 1, 7
MIN_EJERCICIOS_DIA, MAX_EJERCICIOS_DIA = 1, 10
TIPOS_ESPECIALES = (
    "Máxima velocidad",
    "Detención baja",
    "Pausa intraseries",
    "Excéntrica demorada",
)


class ValidacionError(ValueError):
    """Dato inválido. Se usa ValueError como base para capturarlo fácil."""


# ---------------------------------------------------------------- validadores
def _texto(valor, campo, max_len=100, obligatorio=True):
    if valor is None or str(valor).strip() == "":
        if obligatorio:
            raise ValidacionError(f"{campo} es obligatorio")
        return ""
    valor = str(valor).strip()
    if len(valor) > max_len:
        raise ValidacionError(f"{campo} no puede superar {max_len} caracteres")
    return valor


def _entero(valor, campo, minimo, maximo):
    try:
        if isinstance(valor, bool) or (isinstance(valor, float) and not valor.is_integer()):
            raise ValueError
        n = int(valor)
    except (TypeError, ValueError):
        raise ValidacionError(f"{campo}: tiene que ser un número entero")
    if not minimo <= n <= maximo:
        raise ValidacionError(f"{campo}: tiene que estar entre {minimo} y {maximo}")
    return n


def _numero(valor, campo, minimo, maximo):
    try:
        if isinstance(valor, bool):
            raise ValueError
        n = float(valor)
    except (TypeError, ValueError):
        raise ValidacionError(f"{campo}: tiene que ser un número")
    if not minimo <= n <= maximo:
        raise ValidacionError(f"{campo}: tiene que estar entre {minimo} y {maximo}")
    return n


def validar_rpe(valor):
    """RPE: 1 a 10 (lo carga el alumno)."""
    return _entero(valor, "El RPE", 1, 10)


def validar_url_video(url):
    """Link opcional de YouTube. Devuelve '' si no hay."""
    if url is None or str(url).strip() == "":
        return ""
    url = str(url).strip()
    if not re.match(r"^https?://(www\.|m\.)?(youtube\.com|youtu\.be)/\S+$", url):
        raise ValidacionError("El link debe ser de YouTube (youtube.com o youtu.be)")
    return url


# ================================================================== USUARIOS
class Usuario(ABC):
    """Clase abstracta. Cada rol implementa su propio menú (polimorfismo)."""

    ROL = ""

    def __init__(self, nombre, usuario, password=None, id=None, password_hash=None):
        self.__id = id
        self.nombre = nombre
        self.usuario = usuario
        self.__password_hash = None
        if password_hash is not None:          # viene de la base de datos
            self.__password_hash = password_hash
        else:                                  # usuario nuevo: se hashea
            self.cambiar_password(password)

    # --- getters / setters con validación
    @property
    def id(self):
        return self.__id

    @property
    def nombre(self):
        return self.__nombre

    @nombre.setter
    def nombre(self, valor):
        self.__nombre = _texto(valor, "El nombre", 80)

    @property
    def usuario(self):
        return self.__usuario

    @usuario.setter
    def usuario(self, valor):
        valor = _texto(valor, "El usuario", 30)
        if not re.match(r"^[A-Za-z0-9_.]{3,30}$", valor):
            raise ValidacionError("El usuario debe tener 3-30 letras, números, _ o .")
        self.__usuario = valor

    @property
    def password_hash(self):
        return self.__password_hash

    @property
    def rol(self):
        return self.ROL

    # --- contraseña: nunca se guarda en texto plano
    def cambiar_password(self, password):
        if not isinstance(password, str) or len(password) < 6:
            raise ValidacionError("La contraseña debe tener al menos 6 caracteres")
        self.__password_hash = generate_password_hash(password)

    def verificar_password(self, password):
        return check_password_hash(self.__password_hash, password or "")

    # --- polimorfismo
    @abstractmethod
    def obtener_menu(self):
        """Lista de (etiqueta, ruta) según el rol."""

    @abstractmethod
    def puede_editar_prescripcion(self):
        """¿Puede definir series, repeticiones y pesos?"""

    def to_dict(self):
        return {"id": self.__id, "nombre": self.__nombre,
                "usuario": self.__usuario, "rol": self.ROL}


class Entrenador(Usuario):
    ROL = "entrenador"

    def obtener_menu(self):
        return [("Mis alumnos", "/alumnos"), ("Ejercicios", "/ejercicios"),
                ("Rutinas", "/rutinas"), ("Reportes", "/reportes")]

    def puede_editar_prescripcion(self):
        return True


class Alumno(Usuario):
    ROL = "alumno"

    def __init__(self, nombre, usuario, password=None, entrenador_id=None,
                 id=None, password_hash=None):
        super().__init__(nombre, usuario, password, id, password_hash)
        self.entrenador_id = entrenador_id

    def obtener_menu(self):
        return [("Mi rutina", "/mi-rutina"), ("Mi progreso", "/progreso")]

    def puede_editar_prescripcion(self):
        return False        # el alumno solo carga RPE y wellness

    def to_dict(self):
        d = super().to_dict()
        d["entrenador_id"] = self.entrenador_id
        return d


def usuario_desde_fila(fila):
    """Fábrica: arma el objeto correcto (Entrenador o Alumno) desde una fila."""
    if fila is None:
        return None
    if fila["rol"] == "entrenador":
        return Entrenador(fila["nombre"], fila["usuario"], id=fila["id"],
                          password_hash=fila["password_hash"])
    return Alumno(fila["nombre"], fila["usuario"], entrenador_id=fila["entrenador_id"],
                  id=fila["id"], password_hash=fila["password_hash"])


# ================================================================ EJERCICIOS
class Ejercicio:
    """Ejercicio de la biblioteca del entrenador (con video opcional)."""

    def __init__(self, nombre, grupo_muscular="", video_url="", id=None):
        self.__id = id
        self.nombre = nombre
        self.grupo_muscular = grupo_muscular
        self.video_url = video_url

    @property
    def id(self):
        return self.__id

    @property
    def nombre(self):
        return self.__nombre

    @nombre.setter
    def nombre(self, valor):
        self.__nombre = _texto(valor, "El nombre del ejercicio", 100)

    @property
    def grupo_muscular(self):
        return self.__grupo

    @grupo_muscular.setter
    def grupo_muscular(self, valor):
        self.__grupo = _texto(valor, "El grupo muscular", 50, obligatorio=False)

    @property
    def video_url(self):
        return self.__video

    @video_url.setter
    def video_url(self, valor):
        self.__video = validar_url_video(valor)

    def to_dict(self):
        return {"id": self.__id, "nombre": self.__nombre,
                "grupo_muscular": self.__grupo, "video_url": self.__video}


# =================================================================== SERIES
class Serie(ABC):
    """
    Una serie de un ejercicio en una semana.
    El entrenador define reps/carga/pausa; el alumno solo completa el RPE.
    """

    def __init__(self, orden, reps, carga, pausa="", semana=1, rpe=None, id=None):
        self.__id = id
        self.orden = orden
        self.reps = reps
        self.carga = carga
        self.pausa = pausa
        self.semana = semana
        self.rpe = rpe

    @property
    def id(self):
        return self.__id

    @property
    def orden(self):
        return self.__orden

    @orden.setter
    def orden(self, v):
        self.__orden = _entero(v, "El orden de la serie", 1, 50)

    @property
    def reps(self):
        return self.__reps

    @reps.setter
    def reps(self, v):
        self.__reps = _entero(v, "Las repeticiones", 1, 100)

    @property
    def carga(self):
        return self.__carga

    @carga.setter
    def carga(self, v):
        # 0 = peso corporal / sin carga externa
        self.__carga = _numero(v, "La carga", 0, 1000)

    @property
    def pausa(self):
        return self.__pausa

    @pausa.setter
    def pausa(self, v):
        self.__pausa = _texto(v, "La pausa", 20, obligatorio=False)

    @property
    def semana(self):
        return self.__semana

    @semana.setter
    def semana(self, v):
        self.__semana = _entero(v, "La semana", 1, 200)

    @property
    def rpe(self):
        return self.__rpe

    @rpe.setter
    def rpe(self, v):
        self.__rpe = None if v is None else validar_rpe(v)

    @property
    def completada(self):
        return self.__rpe is not None

    @property
    def volumen(self):
        """Repeticiones x carga (base de los reportes de volumen)."""
        return self.__reps * self.__carga

    # --- polimorfismo
    @property
    @abstractmethod
    def tipo_especial(self):
        """None si es normal, o el nombre del tipo de serie especial."""

    @abstractmethod
    def descripcion(self):
        """Texto legible de la serie."""

    @property
    def es_especial(self):
        return self.tipo_especial is not None

    def _base(self):
        return f"{self.__reps} reps x {self.__carga:g} kg"

    # --- utilidades
    @staticmethod
    def crear(orden, reps, carga, pausa="", semana=1, tipo_especial=None,
              rpe=None, id=None):
        """Fábrica: devuelve SerieNormal o SerieEspecial según corresponda."""
        if tipo_especial:
            return SerieEspecial(orden, reps, carga, tipo_especial, pausa, semana, rpe, id)
        return SerieNormal(orden, reps, carga, pausa, semana, rpe, id)

    @staticmethod
    def desde_fila(fila):
        return Serie.crear(fila["orden"], fila["reps"], fila["carga"], fila["pausa"],
                           fila["semana"], fila["tipo_especial"] if fila["es_especial"] else None,
                           fila["rpe"], fila["id"])

    def copiar(self, semana=None):
        """Copia de la prescripción, sin RPE (para 'actualizar semana')."""
        return Serie.crear(self.__orden, self.__reps, self.__carga, self.__pausa,
                           semana or self.__semana, self.tipo_especial)

    def to_dict(self):
        return {"id": self.__id, "orden": self.__orden, "semana": self.__semana,
                "reps": self.__reps, "carga": self.__carga, "pausa": self.__pausa,
                "es_especial": self.es_especial, "tipo_especial": self.tipo_especial,
                "rpe": self.__rpe, "descripcion": self.descripcion()}


class SerieNormal(Serie):
    @property
    def tipo_especial(self):
        return None

    def descripcion(self):
        return self._base()


class SerieEspecial(Serie):
    def __init__(self, orden, reps, carga, tipo, pausa="", semana=1, rpe=None, id=None):
        super().__init__(orden, reps, carga, pausa, semana, rpe, id)
        if tipo not in TIPOS_ESPECIALES:
            raise ValidacionError("Tipo de serie especial inválido. Opciones: "
                                  + ", ".join(TIPOS_ESPECIALES))
        self.__tipo = tipo

    @property
    def tipo_especial(self):
        return self.__tipo

    def descripcion(self):
        return f"{self._base()} ({self.__tipo})"


# ============================================================ COMPOSICIÓN
class Bloque:
    """Un ejercicio del día con todas sus series (de una semana)."""

    def __init__(self, orden, ejercicio, id=None):
        self.__id = id
        self.__orden = _entero(orden, "El orden del bloque", 1, MAX_EJERCICIOS_DIA)
        if not isinstance(ejercicio, Ejercicio):
            raise ValidacionError("El bloque necesita un Ejercicio")
        self.__ejercicio = ejercicio
        self.__series = []

    @property
    def id(self):
        return self.__id

    @property
    def orden(self):
        return self.__orden

    @property
    def ejercicio(self):
        return self.__ejercicio

    @property
    def series(self):
        return list(self.__series)      # copia: no se modifica desde afuera

    def agregar_serie(self, serie):
        if not isinstance(serie, Serie):
            raise ValidacionError("Solo se pueden agregar objetos Serie")
        self.__series.append(serie)

    def volumen(self):
        return sum(s.volumen for s in self.__series)

    def to_dict(self):
        return {"id": self.__id, "orden": self.__orden,
                "ejercicio": self.__ejercicio.to_dict(),
                "series": [s.to_dict() for s in self.__series]}


class Dia:
    """Un día de la rutina: calentamiento propio + hasta 10 bloques."""

    def __init__(self, numero, calentamiento_movilidad="", calentamiento_activacion="",
                 id=None):
        self.__id = id
        self.__numero = _entero(numero, "El número de día", MIN_DIAS, MAX_DIAS)
        self.calentamiento_movilidad = calentamiento_movilidad
        self.calentamiento_activacion = calentamiento_activacion
        self.__bloques = []

    @property
    def id(self):
        return self.__id

    @property
    def numero(self):
        return self.__numero

    @property
    def calentamiento_movilidad(self):
        return self.__mov

    @calentamiento_movilidad.setter
    def calentamiento_movilidad(self, v):
        self.__mov = _texto(v, "La movilidad articular", 500, obligatorio=False)

    @property
    def calentamiento_activacion(self):
        return self.__act

    @calentamiento_activacion.setter
    def calentamiento_activacion(self, v):
        self.__act = _texto(v, "La activación", 500, obligatorio=False)

    @property
    def bloques(self):
        return list(self.__bloques)

    def agregar_bloque(self, bloque):
        if not isinstance(bloque, Bloque):
            raise ValidacionError("Solo se pueden agregar objetos Bloque")
        if len(self.__bloques) >= MAX_EJERCICIOS_DIA:
            raise ValidacionError(f"Un día no puede tener más de {MAX_EJERCICIOS_DIA} ejercicios")
        self.__bloques.append(bloque)

    def volumen(self):
        return sum(b.volumen() for b in self.__bloques)

    def to_dict(self):
        return {"id": self.__id, "numero": self.__numero,
                "calentamiento_movilidad": self.__mov,
                "calentamiento_activacion": self.__act,
                "bloques": [b.to_dict() for b in self.__bloques]}


class Rutina:
    """Rutina de un alumno: 1 a 7 días, con semana actual."""

    def __init__(self, nombre, semana_actual=1, alumno_id=None, entrenador_id=None,
                 id=None):
        self.__id = id
        self.nombre = nombre
        self.semana_actual = semana_actual
        self.alumno_id = alumno_id
        self.entrenador_id = entrenador_id
        self.__dias = []

    @property
    def id(self):
        return self.__id

    @property
    def nombre(self):
        return self.__nombre

    @nombre.setter
    def nombre(self, v):
        self.__nombre = _texto(v, "El nombre de la rutina", 60)

    @property
    def semana_actual(self):
        return self.__semana

    @semana_actual.setter
    def semana_actual(self, v):
        self.__semana = _entero(v, "La semana", 1, 200)

    @property
    def dias(self):
        return list(self.__dias)

    def agregar_dia(self, dia):
        if not isinstance(dia, Dia):
            raise ValidacionError("Solo se pueden agregar objetos Dia")
        if len(self.__dias) >= MAX_DIAS:
            raise ValidacionError(f"Una rutina no puede tener más de {MAX_DIAS} días")
        if any(d.numero == dia.numero for d in self.__dias):
            raise ValidacionError(f"El día {dia.numero} ya existe en la rutina")
        self.__dias.append(dia)

    @staticmethod
    def validar_plan(cantidad_dias, ejercicios_por_dia):
        """
        Paso 1 del asistente de creación.
          cantidad_dias:      entero 1-7
          ejercicios_por_dia: un entero 1-10 (igual para todos los días)
                              o una lista con un entero 1-10 por día (personalizada)
        Devuelve la lista de cantidades de ejercicios, una por día.
        """
        n = _entero(cantidad_dias, "La cantidad de días", MIN_DIAS, MAX_DIAS)
        if isinstance(ejercicios_por_dia, (list, tuple)):
            if len(ejercicios_por_dia) != n:
                raise ValidacionError(f"Hay que indicar los ejercicios de los {n} días")
            return [_entero(c, f"Los ejercicios del día {i}",
                            MIN_EJERCICIOS_DIA, MAX_EJERCICIOS_DIA)
                    for i, c in enumerate(ejercicios_por_dia, 1)]
        cant = _entero(ejercicios_por_dia, "La cantidad de ejercicios por día",
                       MIN_EJERCICIOS_DIA, MAX_EJERCICIOS_DIA)
        return [cant] * n

    def volumen(self):
        return sum(d.volumen() for d in self.__dias)

    def to_dict(self):
        return {"id": self.__id, "nombre": self.__nombre,
                "semana_actual": self.__semana, "alumno_id": self.alumno_id,
                "entrenador_id": self.entrenador_id,
                "dias": [d.to_dict() for d in self.__dias]}


# ================================================================= WELLNESS
class Wellness:
    """Estado del alumno antes de entrenar. Escala 1 a 5 (5 = mejor)."""

    def __init__(self, dolor, fatiga, sueno, animo, fecha=None, id=None):
        self.__id = id
        self.dolor = dolor
        self.fatiga = fatiga
        self.sueno = sueno
        self.animo = animo
        self.fecha = fecha

    @property
    def id(self):
        return self.__id

    @property
    def dolor(self):
        return self.__dolor

    @dolor.setter
    def dolor(self, v):
        self.__dolor = _entero(v, "El dolor corporal", 1, 5)

    @property
    def fatiga(self):
        return self.__fatiga

    @fatiga.setter
    def fatiga(self, v):
        self.__fatiga = _entero(v, "El cansancio/fatiga mental", 1, 5)

    @property
    def sueno(self):
        return self.__sueno

    @sueno.setter
    def sueno(self, v):
        self.__sueno = _entero(v, "La calidad de sueño", 1, 5)

    @property
    def animo(self):
        return self.__animo

    @animo.setter
    def animo(self, v):
        self.__animo = _entero(v, "El ánimo", 1, 5)

    def promedio(self):
        return round((self.__dolor + self.__fatiga + self.__sueno + self.__animo) / 4, 2)

    def to_dict(self):
        return {"id": self.__id, "dolor": self.__dolor, "fatiga": self.__fatiga,
                "sueno": self.__sueno, "animo": self.__animo,
                "promedio": self.promedio(), "fecha": self.fecha}
