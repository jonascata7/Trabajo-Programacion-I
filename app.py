"""
app.py - Capa web (Flask). Recibe los pedidos, valida permisos, llama a
modelos.py (reglas) y database.py (SQL) y devuelve las pantallas (templates/).
No contiene SQL ni reglas de negocio: solo coordina.
"""
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)

import database as db
from modelos import (TIPOS_ESPECIALES, Alumno, Bloque, Dia, Ejercicio, Entrenador,
                     Rutina, Serie, ValidacionError, Wellness)

app = Flask(__name__)
app.secret_key = "clave-de-desarrollo-cambiar-en-produccion"
db.init_db()


# ------------------------------------------------------------ utilidades
def _msg(e):
    """Mensaje para el usuario: el de validación, o uno genérico."""
    return str(e) if isinstance(e, ValidacionError) else "Datos inválidos, revisá el formulario"


def requiere(rol=None):
    """Decorador: exige sesión iniciada y, opcionalmente, un rol."""
    def deco(f):
        @wraps(f)
        def envoltura(*a, **k):
            if g.usuario is None:
                return redirect(url_for("login"))
            if rol and g.usuario.rol != rol:
                abort(403)
            return f(*a, **k)
        return envoltura
    return deco


@app.before_request
def cargar_usuario():
    uid = session.get("uid")
    g.usuario = db.obtener_usuario_por_id(uid) if uid else None


@app.context_processor
def inyectar():
    u = g.get("usuario")
    return {"usuario": u, "menu": u.obtener_menu() if u else []}   # polimorfismo


@app.errorhandler(403)
@app.errorhandler(404)
def sin_acceso(_e):
    flash("No tenés acceso a esa página o no existe.", "warning")
    return redirect(url_for("inicio"))


def _alumno_propio(alumno_id):
    return next((a for a in db.listar_alumnos(g.usuario.id) if a["id"] == alumno_id), None)


# ------------------------------------------------------------ sesión
@app.route("/")
def inicio():
    if g.usuario is None:
        return redirect(url_for("login"))
    return redirect(url_for("alumnos" if g.usuario.rol == "entrenador" else "mi_rutina"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db.autenticar(request.form.get("usuario", "").strip(), request.form.get("password", ""))
        if u:
            session.clear()
            session["uid"] = u.id
            return redirect(url_for("inicio"))
        flash("Usuario o contraseña incorrectos", "danger")
    return render_template("auth.html", modo="login")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    """Solo los entrenadores se registran solos; los alumnos los crea su entrenador."""
    if request.method == "POST":
        f = request.form
        try:
            db.insertar_usuario(Entrenador(f.get("nombre"), f.get("usuario"), f.get("password")))
            flash("Cuenta creada. Ya podés ingresar.", "success")
            return redirect(url_for("login"))
        except ValueError as e:
            flash(_msg(e), "danger")
    return render_template("auth.html", modo="registro")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------ alumnos (ABM)
@app.route("/alumnos")
@requiere("entrenador")
def alumnos():
    q, orden = request.args.get("q", ""), request.args.get("orden", "nombre")
    return render_template("alumnos.html", lista=db.listar_alumnos(g.usuario.id, q, orden),
                           q=q, orden=orden)


@app.route("/alumnos/nuevo", methods=["POST"])
@requiere("entrenador")
def alumno_nuevo():
    f = request.form
    try:
        db.insertar_usuario(Alumno(f.get("nombre"), f.get("usuario"), f.get("password"),
                                   entrenador_id=g.usuario.id))
        flash("Alumno creado", "success")
    except ValueError as e:
        flash(_msg(e), "danger")
    return redirect(url_for("alumnos"))


@app.route("/alumnos/<int:alumno_id>/editar", methods=["GET", "POST"])
@requiere("entrenador")
def alumno_editar(alumno_id):
    alumno = _alumno_propio(alumno_id)
    if alumno is None:
        abort(404)
    if request.method == "POST":
        try:
            db.actualizar_alumno(alumno_id, g.usuario.id, request.form.get("nombre"),
                                 request.form.get("usuario"))
            flash("Alumno actualizado", "success")
            return redirect(url_for("alumnos"))
        except ValueError as e:
            flash(_msg(e), "danger")
    return render_template("alumno_form.html", alumno=alumno)


@app.route("/alumnos/<int:alumno_id>/eliminar", methods=["POST"])
@requiere("entrenador")
def alumno_eliminar(alumno_id):
    if db.eliminar_alumno(alumno_id, g.usuario.id):
        flash("Alumno eliminado junto con sus rutinas", "success")
    return redirect(url_for("alumnos"))


# ------------------------------------------------------------ biblioteca de ejercicios
@app.route("/ejercicios", methods=["GET", "POST"])
@requiere("entrenador")
def ejercicios():
    if request.method == "POST":
        f = request.form
        try:
            db.guardar_ejercicio(g.usuario.id, Ejercicio(f.get("nombre"), f.get("grupo"), f.get("video")))
            flash("Ejercicio guardado en tu biblioteca", "success")
        except ValueError as e:
            flash(_msg(e), "danger")
        return redirect(url_for("ejercicios"))
    q = request.args.get("q", "")
    return render_template("ejercicios.html", lista=db.listar_ejercicios(g.usuario.id, q), q=q)


@app.route("/ejercicios/<int:ej_id>/eliminar", methods=["POST"])
@requiere("entrenador")
def ejercicio_eliminar(ej_id):
    try:
        db.eliminar_ejercicio(ej_id, g.usuario.id)
        flash("Ejercicio eliminado", "success")
    except ValueError as e:
        flash(_msg(e), "danger")
    return redirect(url_for("ejercicios"))


# ------------------------------------------------------------ rutinas: listado
@app.route("/rutinas")
@requiere("entrenador")
def rutinas():
    return render_template("rutinas.html", lista=db.listar_rutinas(entrenador_id=g.usuario.id))


@app.route("/mi-rutina")
@requiere("alumno")
def mi_rutina():
    return render_template("rutinas.html", lista=db.listar_rutinas(alumno_id=g.usuario.id))


# ------------------------------------------------------------ asistente de creación
@app.route("/rutinas/nueva", methods=["GET", "POST"])
@requiere("entrenador")
def rutina_nueva():
    """Paso 1: alumno, nombre, cantidad de días (1-7) y ejercicios por día (1-10)."""
    lista = db.listar_alumnos(g.usuario.id)
    if request.method == "POST":
        f = request.form
        try:
            alumno_id = int(f.get("alumno_id") or 0)
            if alumno_id not in [a["id"] for a in lista]:
                raise ValidacionError("Elegí un alumno")
            Rutina(f.get("nombre"))                       # valida el nombre
            Rutina.validar_plan(f.get("dias"), 1)         # valida 1 a 7 días
            n = int(f.get("dias"))
            if f.get("modo") == "personalizada":
                cantidades = [f.get(f"ej_{i}") for i in range(1, n + 1)]
            else:
                cantidades = f.get("ej_igual")
            plan = Rutina.validar_plan(n, cantidades)
            session["plan"] = {"alumno_id": alumno_id, "nombre": f.get("nombre").strip(),
                               "cantidades": plan}
            return redirect(url_for("rutina_armar"))
        except ValueError as e:
            flash(_msg(e), "danger")
    return render_template("rutina_nueva.html", alumnos=lista)


@app.route("/rutinas/nueva/armar", methods=["GET", "POST"])
@requiere("entrenador")
def rutina_armar():
    """Paso 2: calentamiento y ejercicios de cada día. Series por defecto: se ajustan después."""
    plan = session.get("plan")
    if not plan:
        return redirect(url_for("rutina_nueva"))
    if request.method == "POST":
        f = request.form
        try:
            rutina = Rutina(plan["nombre"])
            for d, cant in enumerate(plan["cantidades"], 1):
                dia = Dia(d, f.get(f"d{d}_mov"), f.get(f"d{d}_act"))
                for i in range(1, cant + 1):
                    bloque = Bloque(i, Ejercicio(f.get(f"d{d}_e{i}_nombre"), "",
                                                 f.get(f"d{d}_e{i}_video")))
                    try:
                        n_series = int(f.get(f"d{d}_e{i}_series") or 0)
                    except ValueError:
                        n_series = 0
                    if not 1 <= n_series <= 10:
                        raise ValidacionError(f"Día {d}, ejercicio {i}: las series van de 1 a 10")
                    for k in range(1, n_series + 1):
                        bloque.agregar_serie(Serie.crear(k, 10, 0))
                    dia.agregar_bloque(bloque)
                rutina.agregar_dia(dia)
            rid = db.crear_rutina(rutina, g.usuario.id, plan["alumno_id"])
            session.pop("plan", None)
            flash("Rutina creada. Ahora cargá repeticiones, pesos y series especiales.", "success")
            return redirect(url_for("rutina_ver", rid=rid))
        except ValueError as e:
            flash(_msg(e), "danger")
    return render_template("rutina_armar.html", plan=plan,
                           biblioteca=db.listar_ejercicios(g.usuario.id))


# ------------------------------------------------------------ ver / editar rutina
@app.route("/rutinas/<int:rid>")
@requiere()
def rutina_ver(rid):
    if not db.rutina_pertenece_a(rid, g.usuario):
        abort(404)
    semana = request.args.get("semana", type=int)
    rutina = db.cargar_rutina(rid, semana)
    ver = semana or rutina.semana_actual
    entrenador = g.usuario.rol == "entrenador"
    return render_template(
        "rutina.html", rutina=rutina, ver=ver, editable=(ver == rutina.semana_actual),
        wellness={d.id: db.obtener_wellness(d.id, ver) for d in rutina.dias},
        tipos=TIPOS_ESPECIALES, alumnos=db.listar_alumnos(g.usuario.id) if entrenador else [])


@app.route("/rutinas/<int:rid>/bloque/<int:bid>", methods=["POST"])
@requiere()
def bloque_guardar(rid, bid):
    """El entrenador guarda reps/carga/pausa/tipo; el alumno guarda solo el RPE."""
    if not db.rutina_pertenece_a(rid, g.usuario):
        abort(404)
    bloque = next((b for d in db.cargar_rutina(rid).dias for b in d.bloques if b.id == bid), None)
    if bloque is None:
        abort(404)
    f = request.form
    try:
        if g.usuario.puede_editar_prescripcion():
            datos = [(s.id, f.get(f"reps_{s.id}"), f.get(f"carga_{s.id}"),
                      f.get(f"pausa_{s.id}", ""), f.get(f"tipo_{s.id}") or None)
                     for s in bloque.series]
            for _id, reps, carga, pausa, tipo in datos:       # 1) validar todo
                Serie.crear(1, reps, carga, pausa, 1, tipo)
            for _id, reps, carga, pausa, tipo in datos:       # 2) recién guardar
                db.actualizar_prescripcion_serie(_id, g.usuario.id, reps, carga, pausa, tipo)
        else:
            for s in bloque.series:
                if f.get(f"rpe_{s.id}"):
                    db.registrar_rpe(s.id, g.usuario.id, f.get(f"rpe_{s.id}"))
        flash("Guardado", "success")
    except ValueError as e:
        flash(_msg(e), "danger")
    return redirect(url_for("rutina_ver", rid=rid) + f"#b{bid}")


@app.route("/rutinas/<int:rid>/dia/<int:did>/wellness", methods=["POST"])
@requiere("alumno")
def wellness_guardar(rid, did):
    f = request.form
    try:
        w = Wellness(f.get("dolor"), f.get("fatiga"), f.get("sueno"), f.get("animo"))
        if not db.registrar_wellness(did, g.usuario.id, w):
            abort(404)
        flash("¡Gracias! Se guardó cómo te sentís hoy", "success")
    except ValueError as e:
        flash(_msg(e), "danger")
    return redirect(url_for("rutina_ver", rid=rid))


@app.route("/rutinas/<int:rid>/nueva-semana", methods=["POST"])
@requiere("entrenador")
def rutina_semana(rid):
    n = db.nueva_semana(rid, g.usuario.id)
    if n is None:
        abort(404)
    flash(f"Ahora estás en la semana {n}. Ajustá los pesos.", "success")
    return redirect(url_for("rutina_ver", rid=rid))


@app.route("/rutinas/<int:rid>/duplicar", methods=["POST"])
@requiere("entrenador")
def rutina_duplicar(rid):
    try:
        nuevo = db.duplicar_rutina(rid, g.usuario.id, int(request.form.get("alumno_id") or 0),
                                   request.form.get("nombre"))
    except ValueError as e:
        flash(_msg(e), "danger")
        return redirect(url_for("rutina_ver", rid=rid))
    if nuevo is None:
        abort(404)
    flash("Rutina copiada como plantilla (semana 1)", "success")
    return redirect(url_for("rutina_ver", rid=nuevo))


@app.route("/rutinas/<int:rid>/eliminar", methods=["POST"])
@requiere("entrenador")
def rutina_eliminar(rid):
    if db.eliminar_rutina(rid, g.usuario.id):
        flash("Rutina eliminada", "success")
    return redirect(url_for("rutinas"))


# ------------------------------------------------------------ reportes
@app.route("/reportes")
@requiere("entrenador")
def reportes():
    return render_template("reportes.html", resumen=db.resumen_alumnos(g.usuario.id))


@app.route("/progreso")
@app.route("/progreso/<int:alumno_id>")
@requiere()
def progreso(alumno_id=None):
    u = g.usuario
    if u.rol == "alumno":
        if alumno_id not in (None, u.id):
            abort(403)
        alumno_id, entrenador_id, nombre = u.id, u.entrenador_id, u.nombre
    else:
        a = _alumno_propio(alumno_id)
        if a is None:
            abort(404)
        entrenador_id, nombre = u.id, a["nombre"]
    lista = db.listar_ejercicios(entrenador_id)
    ej_id = request.args.get("ejercicio", type=int) or (lista[0]["id"] if lista else None)
    rutinas_ = db.listar_rutinas(alumno_id=alumno_id)
    return render_template(
        "progreso.html", nombre=nombre, ejercicios=lista, ej_id=ej_id,
        carga=db.progreso_carga(alumno_id, ej_id) if ej_id else [],
        rpe_sem=db.rpe_promedio_por_semana(rutinas_[0]["id"]) if rutinas_ else [],
        cruce=db.wellness_vs_rpe(alumno_id))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
