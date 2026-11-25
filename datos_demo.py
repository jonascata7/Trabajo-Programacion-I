"""
datos_demo.py - Carga datos de prueba (entrenador, 10 alumnos, 12 ejercicios,
10 rutinas con historial de 2 semanas, RPE y wellness).
Ejecutar UNA vez:  python datos_demo.py
Usuarios:  entrenador "juan" / alumnos "alumno1" ... "alumno10"  -  clave: demo1234
"""
import random
from urllib.parse import quote_plus

import database as db
from modelos import Alumno, Bloque, Dia, Ejercicio, Entrenador, Rutina, Serie, Wellness

EJERCICIOS = [("Swing corto", "Cadera"), ("Peso muerto sumo", "Piernas"),
              ("Press en banco plano", "Pecho"), ("Sentadillas búlgaras", "Piernas"),
              ("Pulldown en polea", "Espalda"), ("Russian twist en landmine", "Core"),
              ("Vuelos laterales", "Hombros"), ("Hip thrust con barra", "Glúteos"),
              ("Chin ups", "Espalda"), ("Ab wheel", "Core"),
              ("Press Arnold", "Hombros"), ("Tríceps francés", "Brazos")]
NOMBRES = ["Gian Leone", "Lucía Pérez", "Martín Gómez", "Sofía Díaz", "Tomás Ruiz",
           "Camila Torres", "Nicolás Sosa", "Valentina Rojas", "Agustín Molina", "Julieta Vega"]


def armar_rutina(i):
    r = Rutina("Fuerza Nov26")
    for d in range(1, 4):
        dia = Dia(d, "Rotaciones de cadera 10 / Movilidad escapular 10", "Bird dog 10 / Puente de glúteos 10")
        for j in range(1, 5):
            nombre, grupo = EJERCICIOS[(d * 4 + j + i) % len(EJERCICIOS)]
            b = Bloque(j, Ejercicio(nombre, grupo, "https://www.youtube.com/results?search_query=" + quote_plus(nombre)))
            base = random.randrange(20, 100, 5)
            for k, reps in enumerate([8, 8, 6], 1):
                especial = "Detención baja" if (j == 2 and k == 1) else None
                b.agregar_serie(Serie.crear(k, reps, base, "1'30''", 1, especial))
            dia.agregar_bloque(b)
        r.agregar_dia(dia)
    return r


def simular(rid, aid, rpe_min, rpe_max):
    """El alumno carga wellness en cada día y RPE en cada serie."""
    for dia in db.cargar_rutina(rid).dias:
        db.registrar_wellness(dia.id, aid, Wellness(*[random.randint(2, 5) for _ in range(4)]))
        for b in dia.bloques:
            for s in b.series:
                db.registrar_rpe(s.id, aid, random.randint(rpe_min, rpe_max))


def main():
    db.init_db()
    if db.autenticar("juan", "demo1234"):
        print("Los datos demo ya existen. Borrá entrenamiento.db si querés empezar de cero.")
        return
    random.seed(7)
    eid = db.insertar_usuario(Entrenador("Juan Bustos", "juan", "demo1234"))
    for n, g in EJERCICIOS:
        db.guardar_ejercicio(eid, Ejercicio(n, g, "https://www.youtube.com/results?search_query=" + quote_plus(n)))
    for i, nombre in enumerate(NOMBRES, 1):
        aid = db.insertar_usuario(Alumno(nombre, f"alumno{i}", "demo1234", entrenador_id=eid))
        rid = db.crear_rutina(armar_rutina(i), eid, aid)
        if i <= 7:                                   # semana 1 completa
            simular(rid, aid, 5, 9)
        if i <= 5:                                   # semana 2: más carga y RPE parcial
            db.nueva_semana(rid, eid)
            for dia in db.cargar_rutina(rid).dias:
                for b in dia.bloques:
                    for s in b.series:
                        db.actualizar_prescripcion_serie(s.id, eid, s.reps, s.carga + 5, s.pausa, s.tipo_especial)
            if i <= 3:
                simular(rid, aid, 6, 10)
    print("Listo. Entrenador: juan / demo1234  -  Alumnos: alumno1..alumno10 / demo1234")


if __name__ == "__main__":
    main()
