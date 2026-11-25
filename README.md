# UB Training — Rutinas de entrenamiento (Flask + SQLite)

Aplicación web para que un **entrenador** arme rutinas semanales para sus **alumnos**.
El entrenador define series, repeticiones, pesos y series especiales; el alumno solo
carga **cuánto le costó (RPE 1-10)** y **cómo se siente antes de entrenar** (wellness 1-5).

Proyecto Final — Programación Orientada a Objetos I — Universidad de Belgrano.
Integrantes: _completar_

## Instalación y ejecución (Windows)
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python datos_demo.py      (opcional: carga datos de prueba)
python app.py
```
Abrir http://localhost:5000
(Linux/Mac: `source venv/bin/activate`). La base `entrenamiento.db` se crea sola.

**Usuarios de prueba** (tras `datos_demo.py`): entrenador `juan` · alumnos `alumno1`…`alumno10` · clave `demo1234`.
Un entrenador nuevo se registra desde "Registrate" en la pantalla de login.

## Estructura
| Archivo | Responsabilidad |
|---|---|
| `modelos.py` | Clases POO y todas las validaciones |
| `database.py` | Todo el SQL (consultas con `?`, transacciones, permisos) |
| `app.py` | Rutas Flask, sesiones, permisos por rol |
| `templates/`, `static/` | Pantallas (Jinja2 con herencia, Bootstrap 5, Chart.js) |
| `datos_demo.py` | Datos de prueba |
| `test_todo.py` | Prueba automática de modelos y base |

## POO
- **Herencia / polimorfismo:** `Usuario` (abstracta) → `Entrenador`, `Alumno` (menú y permisos distintos);
  `Serie` (abstracta) → `SerieNormal`, `SerieEspecial` (`descripcion()` distinta).
- **Composición:** `Rutina` → `Dia` → `Bloque` → `Serie`.
- **Encapsulamiento:** atributos privados (`__`) con getters/setters que validan.

## Reglas de negocio
- Rutina de 1 a 7 días; 1 a 10 ejercicios por día (igual para todos o personalizado).
- RPE 1-10 y wellness 1-5 (5 = mejor). Link de video: solo YouTube.
- "Actualizar semana" copia la semana actual (+1) sin RPE; las anteriores quedan de historial.
- Un entrenador solo ve y edita sus alumnos; un alumno solo carga RPE y wellness de su semana actual.

## Decisiones
- **SQLite:** un solo archivo, sin instalar nada, ideal para este alcance.
- **Baja física** (DELETE) con borrado en cascada de las rutinas del alumno.
- **Contraseñas** con hash (`werkzeug.security`), nunca en texto plano.
- **Sin SQL en las rutas:** la capa web no conoce el SQL; la capa de datos valida permisos en cada `WHERE`.

## Pruebas
`python test_todo.py` (debe terminar con `TODO OK`).
