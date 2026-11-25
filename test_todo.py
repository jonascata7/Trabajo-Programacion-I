# Prueba automática de modelos.py y database.py. Usa una base aparte (test.db).
# Ejecutar con:  python test_todo.py
import database as db
from modelos import *
db.DB_PATH = "test.db"
db.init_db()

def debe_fallar(f, *a):
    try: f(*a)
    except ValueError as e: print("  OK error:", e); return
    raise SystemExit("NO FALLÓ: " + f.__name__)

print("1) Usuarios")
eid = db.insertar_usuario(Entrenador("Juan Bustos", "juan.b", "secreto1"))
a1 = db.insertar_usuario(Alumno("Gian Leone", "gian", "clave123", entrenador_id=eid))
a2 = db.insertar_usuario(Alumno("Otra Persona", "otra", "clave123", entrenador_id=eid))
e2 = db.insertar_usuario(Entrenador("Otro Entrenador", "otro.e", "secreto1"))
debe_fallar(db.insertar_usuario, Entrenador("Dup", "juan.b", "secreto1"))
debe_fallar(Entrenador, "X", "ab", "secreto1")
debe_fallar(Entrenador, "X", "valido", "123")
assert db.autenticar("gian", "clave123").rol == "alumno"
assert db.autenticar("gian", "mala") is None
print("  menu alumno:", db.autenticar("gian","clave123").obtener_menu()[0])
print("  listar:", [a["nombre"] for a in db.listar_alumnos(eid, "gi")])

print("2) Plan")
print("  igual:", Rutina.validar_plan(3, 5), "| personalizada:", Rutina.validar_plan(3, [4,6,10]))
debe_fallar(Rutina.validar_plan, 0, 5)
debe_fallar(Rutina.validar_plan, 8, 5)
debe_fallar(Rutina.validar_plan, 3, 11)
debe_fallar(Rutina.validar_plan, 3, [1,2])
debe_fallar(Rutina.validar_plan, 3, [1,2,0])

print("3) Crear rutina")
r = Rutina("Nov26")
d = Dia(1, "Bisagra de cadera con bastón 10", "Bird dog 10")
b = Bloque(1, Ejercicio("Swing corto", "Cadera", "https://youtu.be/abc123"))
b.agregar_serie(Serie.crear(1, 4, 15, "45''/1'"))
b.agregar_serie(Serie.crear(2, 4, 80, "1'30''/2'", tipo_especial="Detención baja"))
d.agregar_bloque(b)
r.agregar_dia(d)
d2 = Dia(2); b2 = Bloque(1, Ejercicio("Chin ups")); b2.agregar_serie(Serie.crear(1, 8, 0)); d2.agregar_bloque(b2); r.agregar_dia(d2)
debe_fallar(Ejercicio, "X", "", "https://google.com")
debe_fallar(Serie.crear, 1, 0, 10)
debe_fallar(Serie.crear, 1, 5, -1)
debe_fallar(Serie.crear, 1, 5, 10, "", 1, "Inventada")
debe_fallar(r.agregar_dia, Dia(1))
dx = Dia(3)
for i in range(1, 11): dx.agregar_bloque(Bloque(i, Ejercicio(f"E{i}")))
debe_fallar(dx.agregar_bloque, Bloque(1, Ejercicio("11")))
debe_fallar(db.crear_rutina, r, e2, a1)          # alumno de otro entrenador
rid = db.crear_rutina(r, eid, a1)
print("  rutina", rid, "| biblioteca:", [e["nombre"] for e in db.listar_ejercicios(eid)])
ru = db.cargar_rutina(rid)
print("  ", [s.descripcion() for s in ru.dias[0].bloques[0].series])

print("4) Permisos por rol")
sid = [s.id for s in ru.dias[0].bloques[0].series][0]
assert db.registrar_rpe(sid, a1, 7) is True
assert db.registrar_rpe(sid, a2, 7) is False         # otro alumno
debe_fallar(db.registrar_rpe, sid, a1, 11)
assert db.actualizar_prescripcion_serie(sid, e2, 5, 50) is False   # otro entrenador
assert db.actualizar_prescripcion_serie(sid, eid, 5, 20, "1'") is True
did = ru.dias[0].id
assert db.registrar_wellness(did, a1, Wellness(5,4,3,5)) is True
assert db.registrar_wellness(did, a2, Wellness(5,4,3,5)) is False
debe_fallar(Wellness, 6, 1, 1, 1)
db.registrar_wellness(did, a1, Wellness(2,2,2,3))    # reemplaza
print("  wellness:", db.obtener_wellness(did, 1).to_dict()["promedio"])

print("5) Nueva semana")
assert db.nueva_semana(rid, e2) is None
print("  semana:", db.nueva_semana(rid, eid))
ru2 = db.cargar_rutina(rid)
print("  ", [(s.descripcion(), s.rpe) for s in ru2.dias[0].bloques[0].series])
ru1 = db.cargar_rutina(rid, semana=1)
print("   historial s1 rpe:", [s.rpe for s in ru1.dias[0].bloques[0].series])

print("6) Duplicar")
nid = db.duplicar_rutina(rid, eid, a2, "Copia")
c = db.cargar_rutina(nid); print("  ", c.semana_actual, c.dias[0].bloques[0].series[1].descripcion(), c.dias[0].bloques[0].series[0].rpe)
assert db.duplicar_rutina(rid, e2, a2, "x") is None

print("7) Reportes")
eje = db.listar_ejercicios(eid, "swing")[0]["id"]
print("  progreso:", db.progreso_carga(a1, eje))
print("  rpe/semana:", db.rpe_promedio_por_semana(rid))
print("  wellness_vs_rpe:", db.wellness_vs_rpe(a1))
for x in db.resumen_alumnos(eid): print("  ", x["alumno"], x["rutina"], x["adherencia_pct"], x["rpe_prom"], x["wellness_prom"], x["alerta"])

print("8) Bajas")
debe_fallar(db.eliminar_ejercicio, eje, eid)
assert db.eliminar_alumno(a1, e2) is False
assert db.eliminar_alumno(a1, eid) is True
print("  rutinas restantes:", [x["nombre"] for x in db.listar_rutinas(entrenador_id=eid)])
print("TODO OK")
