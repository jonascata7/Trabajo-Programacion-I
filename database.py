"""
database.py - Capa de acceso a datos (todo el SQL vive acá).

- Siempre se usan parámetros (?) -> sin inyección SQL.
- `transaccion()` hace commit si todo sale bien y rollback si falla,
  así nunca se olvida el commit ni queda la base a medio escribir.
- Las funciones reciben el id del entrenador/alumno y lo usan en el WHERE:
  los permisos se validan acá, no solo en el menú.
"""
import sqlite3
from contextlib import contextmanager

from modelos import (Alumno, Bloque, Dia, Ejercicio, Rutina, Serie, ValidacionError,
                     Wellness, usuario_desde_fila, validar_rpe)

DB_PATH = "entrenamiento.db"


# ---------------------------------------------------------------- conexión
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # SQLite lo trae apagado
    return conn


@contextmanager
def transaccion():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with transaccion() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre        TEXT NOT NULL,
            usuario       TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            rol           TEXT NOT NULL CHECK (rol IN ('entrenador','alumno')),
            entrenador_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ejercicios (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            entrenador_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            nombre         TEXT NOT NULL,
            grupo_muscular TEXT,
            video_url      TEXT,
            UNIQUE (entrenador_id, nombre COLLATE NOCASE)
        );
        CREATE TABLE IF NOT EXISTS rutinas (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre        TEXT NOT NULL,
            entrenador_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            alumno_id     INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            semana_actual INTEGER NOT NULL DEFAULT 1,
            activa        INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS dias (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            rutina_id                INTEGER NOT NULL REFERENCES rutinas(id) ON DELETE CASCADE,
            numero                   INTEGER NOT NULL CHECK (numero BETWEEN 1 AND 7),
            calentamiento_movilidad  TEXT,
            calentamiento_activacion TEXT,
            UNIQUE (rutina_id, numero)
        );
        CREATE TABLE IF NOT EXISTS bloques (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            dia_id       INTEGER NOT NULL REFERENCES dias(id) ON DELETE CASCADE,
            orden        INTEGER NOT NULL CHECK (orden BETWEEN 1 AND 10),
            ejercicio_id INTEGER NOT NULL REFERENCES ejercicios(id),
            UNIQUE (dia_id, orden)
        );
        CREATE TABLE IF NOT EXISTS series (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            bloque_id     INTEGER NOT NULL REFERENCES bloques(id) ON DELETE CASCADE,
            semana        INTEGER NOT NULL,
            orden         INTEGER NOT NULL,
            reps          INTEGER NOT NULL,
            carga         REAL NOT NULL DEFAULT 0,
            pausa         TEXT,
            es_especial   INTEGER NOT NULL DEFAULT 0,
            tipo_especial TEXT,
            rpe           INTEGER CHECK (rpe IS NULL OR rpe BETWEEN 1 AND 10)
        );
        CREATE TABLE IF NOT EXISTS wellness (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            dia_id INTEGER NOT NULL REFERENCES dias(id) ON DELETE CASCADE,
            semana INTEGER NOT NULL,
            dolor  INTEGER NOT NULL CHECK (dolor  BETWEEN 1 AND 5),
            fatiga INTEGER NOT NULL CHECK (fatiga BETWEEN 1 AND 5),
            sueno  INTEGER NOT NULL CHECK (sueno  BETWEEN 1 AND 5),
            animo  INTEGER NOT NULL CHECK (animo  BETWEEN 1 AND 5),
            fecha  TEXT NOT NULL DEFAULT CURRENT_DATE,
            UNIQUE (dia_id, semana)
        );
        """)


# ================================================================ USUARIOS
def insertar_usuario(usuario):
    """Alta de Entrenador o Alumno (recibe el objeto). Devuelve el nuevo id."""
    entrenador_id = getattr(usuario, "entrenador_id", None)
    if usuario.rol == "alumno" and entrenador_id is None:
        raise ValidacionError("Un alumno necesita un entrenador")
    try:
        with transaccion() as conn:
            cur = conn.execute(
                "INSERT INTO usuarios (nombre, usuario, password_hash, rol, entrenador_id)"
                " VALUES (?,?,?,?,?)",
                (usuario.nombre, usuario.usuario, usuario.password_hash,
                 usuario.rol, entrenador_id))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValidacionError("Ese nombre de usuario ya existe")


def obtener_usuario_por_id(usuario_id):
    with transaccion() as conn:
        fila = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    return usuario_desde_fila(fila)


def autenticar(nombre_usuario, password):
    """Devuelve el objeto Usuario si las credenciales son correctas, si no None."""
    with transaccion() as conn:
        fila = conn.execute("SELECT * FROM usuarios WHERE usuario=?",
                            (nombre_usuario,)).fetchone()
    usuario = usuario_desde_fila(fila)
    if usuario is not None and usuario.verificar_password(password):
        return usuario
    return None


ORDEN_ALUMNOS = {"nombre": "nombre", "usuario": "usuario", "id": "id"}


def listar_alumnos(entrenador_id, busqueda="", orden="nombre"):
    """Alumnos de un entrenador, con búsqueda y orden (RF4)."""
    columna = ORDEN_ALUMNOS.get(orden, "nombre")        # lista blanca: evita inyección
    patron = f"%{busqueda.strip()}%"
    with transaccion() as conn:
        filas = conn.execute(
            f"SELECT id, nombre, usuario FROM usuarios WHERE entrenador_id=? AND rol='alumno'"
            f" AND (nombre LIKE ? OR usuario LIKE ?) ORDER BY {columna} COLLATE NOCASE",
            (entrenador_id, patron, patron)).fetchall()
    return [dict(f) for f in filas]


def actualizar_alumno(alumno_id, entrenador_id, nombre, usuario):
    # Se valida creando un Alumno temporal (reutiliza los setters)
    temp = Alumno(nombre, usuario, password="temporal", entrenador_id=entrenador_id)
    try:
        with transaccion() as conn:
            cur = conn.execute(
                "UPDATE usuarios SET nombre=?, usuario=? WHERE id=? AND entrenador_id=?",
                (temp.nombre, temp.usuario, alumno_id, entrenador_id))
            return cur.rowcount > 0
    except sqlite3.IntegrityError:
        raise ValidacionError("Ese nombre de usuario ya existe")


def eliminar_alumno(alumno_id, entrenador_id):
    """Baja física: borra también sus rutinas, series y wellness (CASCADE)."""
    with transaccion() as conn:
        cur = conn.execute("DELETE FROM usuarios WHERE id=? AND entrenador_id=? AND rol='alumno'",
                           (alumno_id, entrenador_id))
        return cur.rowcount > 0


# =============================================================== EJERCICIOS
def listar_ejercicios(entrenador_id, busqueda=""):
    with transaccion() as conn:
        filas = conn.execute(
            "SELECT * FROM ejercicios WHERE entrenador_id=? AND nombre LIKE ?"
            " ORDER BY nombre COLLATE NOCASE",
            (entrenador_id, f"%{busqueda.strip()}%")).fetchall()
    return [dict(f) for f in filas]


def _obtener_o_crear_ejercicio(conn, entrenador_id, ejercicio):
    """Si el ejercicio ya está en la biblioteca lo reutiliza; si no, lo guarda."""
    fila = conn.execute(
        "SELECT id, video_url FROM ejercicios WHERE entrenador_id=? AND nombre=? COLLATE NOCASE",
        (entrenador_id, ejercicio.nombre)).fetchone()
    if fila:
        if ejercicio.video_url and ejercicio.video_url != fila["video_url"]:
            conn.execute("UPDATE ejercicios SET video_url=? WHERE id=?",
                         (ejercicio.video_url, fila["id"]))
        return fila["id"]
    cur = conn.execute(
        "INSERT INTO ejercicios (entrenador_id, nombre, grupo_muscular, video_url)"
        " VALUES (?,?,?,?)",
        (entrenador_id, ejercicio.nombre, ejercicio.grupo_muscular, ejercicio.video_url))
    return cur.lastrowid


def guardar_ejercicio(entrenador_id, ejercicio):
    with transaccion() as conn:
        return _obtener_o_crear_ejercicio(conn, entrenador_id, ejercicio)


def actualizar_ejercicio(ejercicio_id, entrenador_id, ejercicio):
    try:
        with transaccion() as conn:
            cur = conn.execute(
                "UPDATE ejercicios SET nombre=?, grupo_muscular=?, video_url=?"
                " WHERE id=? AND entrenador_id=?",
                (ejercicio.nombre, ejercicio.grupo_muscular, ejercicio.video_url,
                 ejercicio_id, entrenador_id))
            return cur.rowcount > 0
    except sqlite3.IntegrityError:
        raise ValidacionError("Ya tenés un ejercicio con ese nombre")


def eliminar_ejercicio(ejercicio_id, entrenador_id):
    try:
        with transaccion() as conn:
            cur = conn.execute("DELETE FROM ejercicios WHERE id=? AND entrenador_id=?",
                               (ejercicio_id, entrenador_id))
            return cur.rowcount > 0
    except sqlite3.IntegrityError:
        raise ValidacionError("El ejercicio está usado en alguna rutina y no se puede borrar")


# ================================================================ RUTINAS
def crear_rutina(rutina, entrenador_id, alumno_id):
    """
    Guarda la rutina completa (días, bloques, series) en UNA transacción:
    si algo falla, no queda nada a medio crear. Devuelve el id de la rutina.
    """
    with transaccion() as conn:
        dueno = conn.execute(
            "SELECT 1 FROM usuarios WHERE id=? AND entrenador_id=? AND rol='alumno'",
            (alumno_id, entrenador_id)).fetchone()
        if dueno is None:
            raise ValidacionError("El alumno no pertenece a este entrenador")

        cur = conn.execute(
            "INSERT INTO rutinas (nombre, entrenador_id, alumno_id, semana_actual)"
            " VALUES (?,?,?,?)",
            (rutina.nombre, entrenador_id, alumno_id, rutina.semana_actual))
        rutina_id = cur.lastrowid

        for dia in rutina.dias:
            cur = conn.execute(
                "INSERT INTO dias (rutina_id, numero, calentamiento_movilidad,"
                " calentamiento_activacion) VALUES (?,?,?,?)",
                (rutina_id, dia.numero, dia.calentamiento_movilidad,
                 dia.calentamiento_activacion))
            dia_id = cur.lastrowid
            for bloque in dia.bloques:
                ej_id = _obtener_o_crear_ejercicio(conn, entrenador_id, bloque.ejercicio)
                cur = conn.execute(
                    "INSERT INTO bloques (dia_id, orden, ejercicio_id) VALUES (?,?,?)",
                    (dia_id, bloque.orden, ej_id))
                bloque_id = cur.lastrowid
                for s in bloque.series:
                    conn.execute(
                        "INSERT INTO series (bloque_id, semana, orden, reps, carga, pausa,"
                        " es_especial, tipo_especial) VALUES (?,?,?,?,?,?,?,?)",
                        (bloque_id, s.semana, s.orden, s.reps, s.carga, s.pausa,
                         int(s.es_especial), s.tipo_especial))
        return rutina_id


def cargar_rutina(rutina_id, semana=None):
    """Reconstruye la rutina como objetos (Rutina > Dia > Bloque > Serie)."""
    with transaccion() as conn:
        r = conn.execute("SELECT * FROM rutinas WHERE id=?", (rutina_id,)).fetchone()
        if r is None:
            return None
        semana = semana or r["semana_actual"]
        rutina = Rutina(r["nombre"], r["semana_actual"], r["alumno_id"],
                        r["entrenador_id"], r["id"])
        dias = conn.execute("SELECT * FROM dias WHERE rutina_id=? ORDER BY numero",
                            (rutina_id,)).fetchall()
        for d in dias:
            dia = Dia(d["numero"], d["calentamiento_movilidad"] or "",
                      d["calentamiento_activacion"] or "", d["id"])
            bloques = conn.execute(
                "SELECT b.id, b.orden, e.id AS eid, e.nombre, e.grupo_muscular, e.video_url"
                " FROM bloques b JOIN ejercicios e ON e.id=b.ejercicio_id"
                " WHERE b.dia_id=? ORDER BY b.orden", (d["id"],)).fetchall()
            for b in bloques:
                ej = Ejercicio(b["nombre"], b["grupo_muscular"] or "",
                               b["video_url"] or "", b["eid"])
                bloque = Bloque(b["orden"], ej, b["id"])
                series = conn.execute(
                    "SELECT * FROM series WHERE bloque_id=? AND semana=? ORDER BY orden",
                    (b["id"], semana)).fetchall()
                for s in series:
                    bloque.agregar_serie(Serie.desde_fila(s))
                dia.agregar_bloque(bloque)
            rutina.agregar_dia(dia)
        return rutina


def listar_rutinas(entrenador_id=None, alumno_id=None):
    """Rutinas de un entrenador o de un alumno (con el nombre del alumno)."""
    if (entrenador_id is None) == (alumno_id is None):
        raise ValueError("Indicar entrenador_id o alumno_id (uno solo)")
    campo, valor = ("r.entrenador_id", entrenador_id) if entrenador_id else ("r.alumno_id", alumno_id)
    with transaccion() as conn:
        filas = conn.execute(
            f"SELECT r.id, r.nombre, r.semana_actual, r.activa, u.nombre AS alumno"
            f" FROM rutinas r JOIN usuarios u ON u.id=r.alumno_id"
            f" WHERE {campo}=? ORDER BY r.id DESC", (valor,)).fetchall()
    return [dict(f) for f in filas]


def rutina_pertenece_a(rutina_id, usuario):
    """Permiso de lectura: el entrenador dueño o el alumno asignado."""
    campo = "entrenador_id" if usuario.rol == "entrenador" else "alumno_id"
    with transaccion() as conn:
        return conn.execute(f"SELECT 1 FROM rutinas WHERE id=? AND {campo}=?",
                            (rutina_id, usuario.id)).fetchone() is not None


def eliminar_rutina(rutina_id, entrenador_id):
    with transaccion() as conn:
        cur = conn.execute("DELETE FROM rutinas WHERE id=? AND entrenador_id=?",
                           (rutina_id, entrenador_id))
        return cur.rowcount > 0


def nueva_semana(rutina_id, entrenador_id):
    """
    'Actualizar semana': copia las series de la semana actual con semana+1
    (sin RPE) y avanza la semana. Las anteriores quedan como historial.
    Devuelve el nuevo número de semana, o None si la rutina no es del entrenador.
    """
    with transaccion() as conn:
        r = conn.execute("SELECT semana_actual FROM rutinas WHERE id=? AND entrenador_id=?",
                         (rutina_id, entrenador_id)).fetchone()
        if r is None:
            return None
        actual, nueva = r["semana_actual"], r["semana_actual"] + 1
        conn.execute(
            "INSERT INTO series (bloque_id, semana, orden, reps, carga, pausa,"
            " es_especial, tipo_especial, rpe)"
            " SELECT s.bloque_id, ?, s.orden, s.reps, s.carga, s.pausa,"
            "        s.es_especial, s.tipo_especial, NULL"
            " FROM series s JOIN bloques b ON b.id=s.bloque_id JOIN dias d ON d.id=b.dia_id"
            " WHERE d.rutina_id=? AND s.semana=?", (nueva, rutina_id, actual))
        conn.execute("UPDATE rutinas SET semana_actual=? WHERE id=?", (nueva, rutina_id))
        return nueva


def duplicar_rutina(rutina_id, entrenador_id, alumno_destino_id, nombre_nuevo):
    """'Nueva rutina' usando otra como plantilla: copia estructura, semana 1, sin RPE."""
    origen = cargar_rutina(rutina_id)
    if origen is None or origen.entrenador_id != entrenador_id:
        return None
    nueva = Rutina(nombre_nuevo, 1)
    for d in origen.dias:
        nd = Dia(d.numero, d.calentamiento_movilidad, d.calentamiento_activacion)
        for b in d.bloques:
            nb = Bloque(b.orden, b.ejercicio)
            for s in b.series:
                nb.agregar_serie(s.copiar(semana=1))
            nd.agregar_bloque(nb)
        nueva.agregar_dia(nd)
    return crear_rutina(nueva, entrenador_id, alumno_destino_id)


# ---------------------------------------------- escritura según el rol
_SERIE_DEL_ENTRENADOR = (
    " bloque_id IN (SELECT b.id FROM bloques b JOIN dias d ON d.id=b.dia_id"
    " JOIN rutinas r ON r.id=d.rutina_id WHERE r.entrenador_id=?)")


def actualizar_prescripcion_serie(serie_id, entrenador_id, reps, carga, pausa="",
                                  tipo_especial=None):
    """SOLO ENTRENADOR: reps, carga, pausa y tipo de serie especial."""
    s = Serie.crear(1, reps, carga, pausa, 1, tipo_especial or None)   # valida
    with transaccion() as conn:
        cur = conn.execute(
            "UPDATE series SET reps=?, carga=?, pausa=?, es_especial=?, tipo_especial=?"
            f" WHERE id=? AND {_SERIE_DEL_ENTRENADOR}",
            (s.reps, s.carga, s.pausa, int(s.es_especial), s.tipo_especial,
             serie_id, entrenador_id))
        return cur.rowcount > 0


def registrar_rpe(serie_id, alumno_id, rpe):
    """SOLO ALUMNO: cuánto le costó (1-10). Únicamente series de su semana actual."""
    rpe = validar_rpe(rpe)
    with transaccion() as conn:
        cur = conn.execute(
            "UPDATE series SET rpe=? WHERE id=? AND bloque_id IN ("
            " SELECT b.id FROM bloques b JOIN dias d ON d.id=b.dia_id"
            " JOIN rutinas r ON r.id=d.rutina_id"
            " WHERE r.alumno_id=? AND r.semana_actual=series.semana)",
            (rpe, serie_id, alumno_id))
        return cur.rowcount > 0


def registrar_wellness(dia_id, alumno_id, wellness):
    """SOLO ALUMNO: estado previo al entrenamiento. Si ya cargó ese día, lo reemplaza."""
    with transaccion() as conn:
        f = conn.execute(
            "SELECT r.semana_actual FROM dias d JOIN rutinas r ON r.id=d.rutina_id"
            " WHERE d.id=? AND r.alumno_id=?", (dia_id, alumno_id)).fetchone()
        if f is None:
            return False
        conn.execute(
            "INSERT INTO wellness (dia_id, semana, dolor, fatiga, sueno, animo)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(dia_id, semana) DO UPDATE SET dolor=excluded.dolor,"
            " fatiga=excluded.fatiga, sueno=excluded.sueno, animo=excluded.animo,"
            " fecha=CURRENT_DATE",
            (dia_id, f["semana_actual"], wellness.dolor, wellness.fatiga,
             wellness.sueno, wellness.animo))
        return True


def obtener_wellness(dia_id, semana):
    with transaccion() as conn:
        f = conn.execute("SELECT * FROM wellness WHERE dia_id=? AND semana=?",
                         (dia_id, semana)).fetchone()
    if f is None:
        return None
    return Wellness(f["dolor"], f["fatiga"], f["sueno"], f["animo"], f["fecha"], f["id"])


# ================================================================ REPORTES
def progreso_carga(alumno_id, ejercicio_id):
    """Por semana: carga máxima, volumen (reps x carga) y RPE promedio de un ejercicio."""
    with transaccion() as conn:
        filas = conn.execute(
            "SELECT s.semana, MAX(s.carga) AS carga_max,"
            " SUM(s.reps * s.carga) AS volumen, ROUND(AVG(s.rpe), 1) AS rpe_prom"
            " FROM series s JOIN bloques b ON b.id=s.bloque_id"
            " JOIN dias d ON d.id=b.dia_id JOIN rutinas r ON r.id=d.rutina_id"
            " WHERE r.alumno_id=? AND b.ejercicio_id=?"
            " GROUP BY r.id, s.semana ORDER BY s.semana", (alumno_id, ejercicio_id)).fetchall()
    return [dict(f) for f in filas]


def rpe_promedio_por_semana(rutina_id):
    with transaccion() as conn:
        filas = conn.execute(
            "SELECT s.semana, ROUND(AVG(s.rpe), 1) AS rpe_prom,"
            " COUNT(s.rpe) AS completadas, COUNT(*) AS totales"
            " FROM series s JOIN bloques b ON b.id=s.bloque_id JOIN dias d ON d.id=b.dia_id"
            " WHERE d.rutina_id=? GROUP BY s.semana ORDER BY s.semana",
            (rutina_id,)).fetchall()
    return [dict(f) for f in filas]


def wellness_vs_rpe(alumno_id):
    """Cruza cómo llegó el alumno (wellness 1-5, 5 = mejor) con cuánto le costó (RPE)."""
    with transaccion() as conn:
        filas = conn.execute(
            "SELECT d.numero AS dia, w.semana, w.fecha,"
            " ROUND((w.dolor + w.fatiga + w.sueno + w.animo) / 4.0, 2) AS wellness_prom,"
            " (SELECT ROUND(AVG(s.rpe), 1) FROM series s JOIN bloques b ON b.id=s.bloque_id"
            "  WHERE b.dia_id=d.id AND s.semana=w.semana) AS rpe_prom"
            " FROM wellness w JOIN dias d ON d.id=w.dia_id JOIN rutinas r ON r.id=d.rutina_id"
            " WHERE r.alumno_id=? ORDER BY w.fecha, w.semana, d.numero",
            (alumno_id,)).fetchall()
    return [dict(f) for f in filas]


def resumen_alumnos(entrenador_id, rpe_alto=8.0, wellness_bajo=2.5):
    """
    Panel del entrenador: por alumno, adherencia de la semana actual
    (series con RPE / series prescriptas), RPE y wellness promedio, y una alerta.
    """
    with transaccion() as conn:
        filas = conn.execute(
            "SELECT u.id AS alumno_id, u.nombre AS alumno, r.id AS rutina_id,"
            " r.nombre AS rutina, r.semana_actual,"
            " COUNT(s.id) AS series_totales, COUNT(s.rpe) AS series_completadas,"
            " ROUND(AVG(s.rpe), 1) AS rpe_prom"
            " FROM usuarios u"
            " LEFT JOIN rutinas r ON r.alumno_id=u.id AND r.activa=1"
            " LEFT JOIN dias d ON d.rutina_id=r.id"
            " LEFT JOIN bloques b ON b.dia_id=d.id"
            " LEFT JOIN series s ON s.bloque_id=b.id AND s.semana=r.semana_actual"
            " WHERE u.entrenador_id=? AND u.rol='alumno'"
            " GROUP BY u.id, r.id ORDER BY u.nombre COLLATE NOCASE",
            (entrenador_id,)).fetchall()
        resultado = []
        for f in filas:
            item = dict(f)
            total = item["series_totales"]
            item["adherencia_pct"] = round(100 * item["series_completadas"] / total, 1) if total else None
            w = None
            if item["rutina_id"]:
                w = conn.execute(
                    "SELECT ROUND(AVG((w.dolor + w.fatiga + w.sueno + w.animo) / 4.0), 2) AS p"
                    " FROM wellness w JOIN dias d ON d.id=w.dia_id"
                    " WHERE d.rutina_id=? AND w.semana=?",
                    (item["rutina_id"], item["semana_actual"])).fetchone()["p"]
            item["wellness_prom"] = w
            item["alerta"] = bool((item["rpe_prom"] or 0) >= rpe_alto
                                  or (w is not None and w <= wellness_bajo))
            resultado.append(item)
    return resultado
