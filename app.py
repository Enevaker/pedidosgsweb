
import os, sqlite3, json, io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort, g
from werkzeug.security import generate_password_hash, check_password_hash


import secrets
from datetime import timedelta

def generate_token(n=32):
    return secrets.token_urlsafe(n)[:n]

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH   = os.path.join(BASE_DIR, "pedidos.db")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def table_has_column(table, column):
    info = get_db().execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in info)

def init_db():
    db = get_db()
    with open(os.path.join(BASE_DIR, "schema.sql"), "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()

def migrate_db():
    db = get_db()
    # ---- escuelas fields (perfil + paquetería) ----
    esc_cols = [
        ("direccion","TEXT"),
        ("colonia","TEXT"),
        ("codigo_postal","TEXT"),
        ("estado","TEXT"),
        ("referencias","TEXT"),
        # paquetería-foráneos
        ("dest_nombre","TEXT"),
        ("dest_tel","TEXT"),
        ("dest_cp","TEXT"),
        ("dest_colonia","TEXT"),
        ("dest_direccion","TEXT"),
        ("dest_correo","TEXT")
    ]
    for col, ctype in esc_cols:
        if not table_has_column("escuelas", col):
            db.execute(f"ALTER TABLE escuelas ADD COLUMN {col} {ctype}")
            db.commit()

    # ---- pedidos fields (globales del pedido) ----
    ped_cols = [
        ("color_calceta_ninas","TEXT"),
        ("color_zapato_ninas","TEXT"),
        ("color_zapato_ninos","TEXT"),
        ("color_monos","TEXT"),
        ("color_pantalon","TEXT"),
        ("escudos_bordar","INTEGER"),
        ("fechas_entrega","TEXT"),   # JSON list
        ("entrega","TEXT")           # 'Ocurre' | 'Domicilio'
    ]
    for col, ctype in ped_cols:
        if not table_has_column("pedidos", col):
            db.execute(f"ALTER TABLE pedidos ADD COLUMN {col} {ctype}")
            db.commit()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_change_me")
app.teardown_appcontext(close_db)

def query_one(q, args=()):
    return get_db().execute(q, args).fetchone()

def query_all(q, args=()):
    return get_db().execute(q, args).fetchall()

def execute(q, args=()):
    db = get_db()
    cur = db.execute(q, args)
    db.commit()
    return cur.lastrowid

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **k):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*a, **k)
    return wrapper

def role_required(*roles):
    def deco(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*a, **k):
            if not session.get("user_id"):
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("No tienes permisos para acceder aquí.", "error")
                return redirect(url_for("home"))
            return fn(*a, **k)
        return wrapper
    return deco

def ensure_db():
    first_time = not os.path.exists(DB_PATH)

    if first_time:
        init_db()

        # --- datos demo (opcional) ---
        admin_id = execute(
            "INSERT INTO users(name,email,password_hash,role,is_active) VALUES (?,?,?,?,1)",
            ("Admin", "admin@demo.local", generate_password_hash("admin123"), "admin")
        )
        vend_id = execute(
            "INSERT INTO users(name,email,password_hash,role,is_active) VALUES (?,?,?,?,1)",
            ("Vendedora Demo", "vendedora@demo.local", generate_password_hash("demo123"), "vendedora")
        )
        esc_user_id = execute(
            "INSERT INTO users(name,email,password_hash,role,is_active) VALUES (?,?,?,?,1)",
            ("Escuela Demo", "escuela@demo.local", generate_password_hash("demo123"), "escuela")
        )
        paq_id = execute("INSERT INTO paqueterias(nombre,activa) VALUES(?,1)", ("Estafeta",))
        execute("INSERT INTO paqueterias(nombre,activa) VALUES(?,1)", ("DHL",))

        esc_id = execute("""
            INSERT INTO escuelas(nombre,ciudad,grado,contacto,telefono,user_id,vendedora_id, estado)
            VALUES(?,?,?,?,?,?,?,?)
        """, ("Colegio Benito Juárez", "Guadalajara", "Primaria", "Mtra. López", "3312345678", esc_user_id, vend_id, "Jalisco"))

        ninas = json.dumps([{"nombre":"Ana","color_pelo":"Castaño","calceta":"Blanca"}], ensure_ascii=False)
        ninos = json.dumps([{"nombre":"Leo","color_pelo":"Castaño","calceta":"Negra"}], ensure_ascii=False)

        execute("""
            INSERT INTO pedidos(escuela_id,ciudad,grado,ninas_json,ninos_json,comentario,estado,paqueteria_id,created_at,
                                color_calceta_ninas,color_zapato_ninas,color_zapato_ninos,color_monos,color_pantalon,
                                escudos_bordar,fechas_entrega,entrega)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (esc_id, "Guadalajara", "Primaria", ninas, ninos, "Pedido de muestra", "Nuevo", paq_id, datetime.utcnow().isoformat(),
              "Blanca", "Negro", "Negro", "Azul marino", "Azul marino", 5, json.dumps(["25/05/2026","15/06/2026"]), "Ocurre"))
    else:
        migrate_db()

    # --- ensure password_resets table ---
    try:
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        db.commit()
    except Exception:
        # ignorar si la BD está bloqueada u otra condición no crítica
        pass


@app.before_request
def _before():
    ensure_db()

@app.context_processor
def inject_now():
    return {"now": datetime.utcnow()}

@app.get("/")
def home():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    if role == "vendedora":
        return redirect(url_for("vendedora_dashboard"))
    return redirect(url_for("escuela_dashboard"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        user = query_one("SELECT * FROM users WHERE email = ?", (email,))
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Credenciales inválidas", "error")
            return render_template("login.html")
        if not user["is_active"]:
            flash("Usuario inactivo. Contacta al administrador.", "error")
            return render_template("login.html")
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]
        return redirect(url_for("home"))
    return render_template("login.html")

@app.get("/signup")
def signup_form():
    # Solo mostrar si no hay sesión iniciada
    if session.get("user_id"):
        return redirect(url_for("home"))
    return render_template("signup.html")


@app.post("/signup")
def signup_submit():
    name = request.form.get("nombre_escuela","").strip()
    email = request.form.get("email","").strip().lower()
    password = request.form.get("password","")
    if not name or not email or not password:
        flash("Completa nombre, correo y contraseña.", "error")
        return render_template("signup.html")
    exists = query_one("SELECT 1 FROM users WHERE email=?", (email,))
    if exists:
        flash("Ese correo ya está registrado.", "error")
        return render_template("signup.html")
    user_id = execute(
        "INSERT INTO users(name,email,password_hash,role,is_active) VALUES (?,?,?,?,0)",
        (name, email, generate_password_hash(password), "escuela")
    )
    execute(
        "INSERT INTO escuelas(nombre, user_id) VALUES (?,?)",
        (name, user_id)
    )
    flash("Registro enviado. Un administrador revisará y activará tu cuenta.", "ok")
    return redirect(url_for("login"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------- Admin ----------
@app.get("/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    total_pedidos = query_one("SELECT COUNT(*) c FROM pedidos")["c"]
    total_escuelas = query_one("SELECT COUNT(*) c FROM escuelas")["c"]
    total_vendedoras = query_one("SELECT COUNT(*) c FROM users WHERE role='vendedora'")["c"]
    pedidos = query_all("""
        SELECT p.*, e.nombre AS escuela, e.ciudad AS escuela_ciudad, pa.nombre AS paqueteria
        FROM pedidos p
        JOIN escuelas e ON e.id = p.escuela_id
        LEFT JOIN paqueterias pa ON pa.id = p.paqueteria_id
        ORDER BY p.created_at DESC
        LIMIT 10
    """)
    return render_template("admin_dashboard.html",
                           total_pedidos=total_pedidos,
                           total_escuelas=total_escuelas,
                           total_vendedoras=total_vendedoras,
                           pedidos=pedidos)

@app.get("/admin/pedidos")
@login_required
@role_required("admin")
def admin_pedidos():
    pedidos = query_all("""
        SELECT p.*, e.nombre AS escuela, e.ciudad AS escuela_ciudad, pa.nombre AS paqueteria
        FROM pedidos p
        JOIN escuelas e ON e.id = p.escuela_id
        LEFT JOIN paqueterias pa ON pa.id = p.paqueteria_id
        ORDER BY p.created_at DESC
    """)
    paqs = query_all("SELECT * FROM paqueterias WHERE activa=1 ORDER BY nombre")
    estados = ["Nuevo","En revisión","Aprobado","En producción","Listo para envío","Enviado","Entregado","Cancelado"]
    return render_template("admin_pedidos.html", pedidos=pedidos, paqs=paqs, estados=estados)

@app.post("/admin/pedido/<int:pedido_id>/paqueteria")
@login_required
@role_required("admin")
def admin_set_paqueteria(pedido_id):
    paq_id = request.form.get("paqueteria_id")
    execute("UPDATE pedidos SET paqueteria_id=? WHERE id=?", (paq_id, pedido_id))
    flash("Paquetería actualizada.", "ok")
    return redirect(url_for("admin_pedidos"))

@app.post("/admin/pedido/<int:pedido_id>/estado")
@login_required
@role_required("admin")
def admin_set_estado(pedido_id):
    estado = request.form.get("estado","Nuevo")
    execute("UPDATE pedidos SET estado=? WHERE id=?", (estado, pedido_id))
    flash("Estado del pedido actualizado.", "ok")
    return redirect(url_for("admin_pedidos"))

@app.get("/admin/pedido/<int:pedido_id>")
@login_required
@role_required("admin","vendedora","escuela")
def pedido_detalle(pedido_id):
    p = query_one("""
        SELECT p.*, e.nombre AS escuela, e.ciudad AS escuela_ciudad, e.grado AS escuela_grado, e.contacto, e.telefono,
               e.direccion, e.colonia, e.codigo_postal, e.estado AS escuela_estado, e.referencias,
               e.dest_nombre, e.dest_tel, e.dest_cp, e.dest_colonia, e.dest_direccion, e.dest_correo,
               pa.nombre AS paqueteria
        FROM pedidos p
        JOIN escuelas e ON e.id = p.escuela_id
        LEFT JOIN paqueterias pa ON pa.id = p.paqueteria_id
        WHERE p.id = ?
    """, (pedido_id,))
    if not p: abort(404)
    role = session.get("role")
    if role == "escuela":
        esc_user = query_one("SELECT user_id FROM escuelas WHERE id=?", (p["escuela_id"],))
        if not esc_user or esc_user["user_id"] != session["user_id"]:
            abort(403)
    if role == "vendedora":
        esc = query_one("SELECT vendedora_id FROM escuelas WHERE id=?", (p["escuela_id"],))
        if not esc or esc["vendedora_id"] != session["user_id"]:
            abort(403)
    def parse(js):
        try: return json.loads(js) if js else []
        except Exception: return []
    ninas = parse(p["ninas_json"]); ninos = parse(p["ninos_json"])
    fechas = parse(p["fechas_entrega"] or "[]")
    return render_template("pedido_detail.html", p=p, ninas=ninas, ninos=ninos, fechas=fechas)

@app.get("/admin/pedido/<int:pedido_id>/pdf")
@login_required
@role_required("admin")
def pedido_pdf(pedido_id):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as e:
        flash("No se pudo generar PDF (falta dependencia reportlab). Usa el botón Imprimir.", "error")
        return redirect(url_for("pedido_detalle", pedido_id=pedido_id))

    p = query_one("""
        SELECT p.*, e.nombre AS escuela, e.ciudad AS escuela_ciudad, e.grado AS escuela_grado, e.contacto, e.telefono,
               e.direccion, e.colonia, e.codigo_postal, e.estado AS escuela_estado, e.referencias,
               e.dest_nombre, e.dest_tel, e.dest_cp, e.dest_colonia, e.dest_direccion, e.dest_correo,
               pa.nombre AS paqueteria
        FROM pedidos p
        JOIN escuelas e ON e.id = p.escuela_id
        LEFT JOIN paqueterias pa ON pa.id = p.paqueteria_id
        WHERE p.id = ?
    """, (pedido_id,))
    if not p: abort(404)
    def parse(js):
        try: return json.loads(js) if js else []
        except Exception: return []
    ninas = parse(p["ninas_json"]); ninos = parse(p["ninos_json"]); fechas = parse(p["fechas_entrega"] or "[]")
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40
    c.setFont("Helvetica-Bold", 14); c.drawString(40, y, "Pedido - Pedidos GS"); y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Escuela: {p['escuela']}  |  Ciudad: {p['escuela_ciudad']}  |  Grado: {p['escuela_grado']}"); y -= 14
    c.drawString(40, y, f"Contacto: {p['contacto']}  Tel: {p['telefono']}"); y -= 14
    c.drawString(40, y, f"Dirección: {p['direccion'] or ''} {p['colonia'] or ''} CP {p['codigo_postal'] or ''} {p['escuela_estado'] or ''}"); y -= 14
    c.drawString(40, y, f"Paquetería asignada: {p['paqueteria'] or '—'}  |  Entrega: {p['entrega'] or '—'}"); y -= 14
    c.drawString(40, y, f"Calceta niñas: {p['color_calceta_ninas'] or '—'}  Zapato niñas: {p['color_zapato_ninas'] or '—'}  Zapato niños: {p['color_zapato_ninos'] or '—'}"); y -= 14
    c.drawString(40, y, f"Moños: {p['color_monos'] or '—'}  Pantalón: {p['color_pantalon'] or '—'}  Escudos por bordar: {p['escudos_bordar'] or '—'}"); y -= 14
    c.drawString(40, y, f"Fechas de entrega: {', '.join(fechas) if fechas else '—'}"); y -= 20

    def draw_group(title, arr):
        nonlocal y
        c.setFont("Helvetica-Bold", 12); c.drawString(40, y, title); y -= 16; c.setFont("Helvetica", 10)
        for it in arr:
            c.drawString(50, y, f"- {it.get('nombre','')} (Pelo: {it.get('color_pelo','')})")
            y -= 14
            if y < 60: c.showPage(); y = height - 40
    draw_group("Niñas", ninas); y -= 8; draw_group("Niños", ninos)

    y -= 8; c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Comentarios"); y -= 16; c.setFont("Helvetica", 10)
    for line in (p["comentario"] or "").splitlines():
        c.drawString(50, y, line[:100]); y -= 14
        if y < 60: c.showPage(); y = height - 40

    c.showPage(); c.save(); buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"pedido_{pedido_id}.pdf")

# ---------- Vendedora ----------
@app.get("/vendedora")
@login_required
@role_required("vendedora")
def vendedora_dashboard():
    escuelas = query_all("""
        SELECT e.*, (SELECT COUNT(1) FROM pedidos p WHERE p.escuela_id=e.id) AS pedidos_count
        FROM escuelas e WHERE e.vendedora_id = ?
        ORDER BY e.nombre
    """, (session["user_id"],))
    return render_template("vendedora_dashboard.html", escuelas=escuelas)

# ---------- Escuela ----------
@app.get("/escuela")
@login_required
@role_required("escuela")
def escuela_dashboard():
    esc = query_one("SELECT * FROM escuelas WHERE user_id=?", (session["user_id"],))
    pedidos = query_all("""
        SELECT p.*, pa.nombre AS paqueteria
        FROM pedidos p
        LEFT JOIN paqueterias pa ON pa.id=p.paqueteria_id
        WHERE p.escuela_id = (SELECT id FROM escuelas WHERE user_id=?)
        ORDER BY p.created_at DESC
    """, (session["user_id"],))
    return render_template("escuela_dashboard.html", pedidos=pedidos, esc=esc)

@app.get("/escuela/perfil")
@login_required
@role_required("escuela")
def escuela_perfil():
    esc = query_one("SELECT * FROM escuelas WHERE user_id=?", (session["user_id"],))
    return render_template("escuela_perfil.html", esc=esc)

@app.post("/escuela/perfil")
@login_required
@role_required("escuela")
def escuela_perfil_guardar():
    fields = ["nombre","ciudad","grado","contacto","telefono",
              "direccion","colonia","codigo_postal","estado","referencias",
              "dest_nombre","dest_tel","dest_cp","dest_colonia","dest_direccion","dest_correo"]
    data = {f: (request.form.get(f,"") or "").strip() for f in fields}
    execute(f"""
        UPDATE escuelas SET
            nombre=?, ciudad=?, grado=?, contacto=?, telefono=?,
            direccion=?, colonia=?, codigo_postal=?, estado=?, referencias=?,
            dest_nombre=?, dest_tel=?, dest_cp=?, dest_colonia=?, dest_direccion=?, dest_correo=?
        WHERE user_id=?
    """, (*[data[f] for f in fields], session["user_id"]))
    flash("Perfil de escuela actualizado.", "ok")
    return redirect(url_for("escuela_perfil"))

@app.get("/escuela/pedido/nuevo")
@login_required
@role_required("escuela")
def pedido_nuevo():
    esc = query_one("SELECT * FROM escuelas WHERE user_id=?", (session["user_id"],))
    # fechas sugeridas del ejemplo
    fechas = ["25/05/2026","15/06/2026","29/06/2026","06/07/2026","13/07/2026"]
    return render_template("pedido_form.html", esc=esc, fechas=fechas)


@app.post("/escuela/pedido/nuevo")
@login_required
@role_required("escuela")
def pedido_guardar():
    ciudad = request.form.get("ciudad","").strip()
    grado = request.form.get("grado","").strip()
    comentario = request.form.get("comentario","").strip()

    # opciones globales
    color_calceta_ninas = request.form.get("color_calceta_ninas","").strip()
    color_zapato_ninas  = request.form.get("color_zapato_ninas","").strip()
    color_zapato_ninos  = request.form.get("color_zapato_ninos","").strip()
    color_monos         = request.form.get("color_monos","").strip()
    color_pantalon      = request.form.get("color_pantalon","").strip()
    escudos_bordar      = int(request.form.get("escudos_bordar","0") or 0)
    fechas_entrega      = request.form.getlist("fechas_entrega[]")
    entrega             = request.form.get("entrega","")

    def parse_grupo(prefix):
        nombres = request.form.getlist(f"{prefix}[nombre][]")
        pelos = request.form.getlist(f"{prefix}[color_pelo][]")
        items = []
        for n, pelo in zip(nombres, pelos):
            n = (n or "").strip()
            if n:
                items.append({
                    "nombre": n[:30],
                    "color_pelo": (pelo or "")
                })
        return json.dumps(items, ensure_ascii=False)

    ninas_json = parse_grupo("ninas")
    ninos_json = parse_grupo("ninos")

    esc = query_one("SELECT id FROM escuelas WHERE user_id=?", (session["user_id"],))
    if not esc:
        flash("Tu usuario no está vinculado a una escuela.", "error")
        return redirect(url_for("escuela_dashboard"))

    execute("""
        INSERT INTO pedidos(
            escuela_id,ciudad,grado,ninas_json,ninos_json,comentario,estado,created_at,
            color_calceta_ninas,color_zapato_ninas,color_zapato_ninos,color_monos,color_pantalon,escudos_bordar,fechas_entrega,entrega
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        esc["id"], ciudad, grado, ninas_json, ninos_json, comentario, "Nuevo", datetime.utcnow().isoformat(),
        color_calceta_ninas, color_zapato_ninas, color_zapato_ninos, color_monos, color_pantalon, escudos_bordar, json.dumps(fechas_entrega, ensure_ascii=False), entrega
    ))
    flash("Pedido registrado correctamente.", "ok")
    return redirect(url_for("escuela_dashboard"))
# ---------- Paqueterías (Admin) ----------
@app.get("/admin/paqueterias")
@login_required
@role_required("admin")
def admin_paqueterias():
    paqs = query_all("SELECT * FROM paqueterias ORDER BY activa DESC, nombre")
    return render_template("admin_paqueterias.html", paqs=paqs)

@app.post("/admin/paqueteria/nueva")
@login_required
@role_required("admin")
def admin_paq_nueva():
    nombre = request.form.get("nombre","").strip()
    if nombre:
        execute("INSERT INTO paqueterias(nombre,activa) VALUES(?,1)", (nombre,))
        flash("Paquetería agregada.", "ok")
    return redirect(url_for("admin_paqueterias"))

@app.post("/admin/paqueteria/<int:paq_id>/estado")
@login_required
@role_required("admin")
def admin_paq_estado(paq_id):
    activa = 1 if request.form.get("activa")=="1" else 0
    execute("UPDATE paqueterias SET activa=? WHERE id=?", (activa, paq_id))
    flash("Paquetería actualizada.", "ok")
    return redirect(url_for("admin_paqueterias"))

@app.errorhandler(404)
def _404(e):
    return render_template("error.html", code=404, msg="No encontrado"), 404

@app.errorhandler(403)
def _403(e):
    return render_template("error.html", code=403, msg="Acceso prohibido"), 403

@app.errorhandler(500)
def _500(e):
    return render_template("error.html", code=500, msg="Error del servidor"), 500


@app.get("/admin/validar_cuentas")
@login_required
@role_required("admin")
def admin_validar_cuentas():
    pendientes = query_all(
        "SELECT u.*, e.nombre AS escuela_nombre, e.ciudad FROM users u "
        "LEFT JOIN escuelas e ON e.user_id = u.id "
        "WHERE u.role='escuela' AND u.is_active=0 ORDER BY u.id DESC"
    )
    activos = query_all(
        "SELECT u.*, e.nombre AS escuela_nombre, e.ciudad FROM users u "
        "LEFT JOIN escuelas e ON e.user_id = u.id "
        "WHERE u.role='escuela' AND u.is_active=1 ORDER BY u.id DESC"
    )
    return render_template("admin_validar_cuentas.html", pendientes=pendientes, activos=activos)

@app.post("/admin/validar_cuentas/<int:user_id>/<action>")
@login_required
@role_required("admin")
def admin_validar_accion(user_id, action):
    u = query_one("SELECT * FROM users WHERE id=?", (user_id,))
    if not u or u["role"] != "escuela":
        abort(404)
    if action == "aprobar":
        execute("UPDATE users SET is_active=1 WHERE id=?", (user_id,))
        flash("Cuenta aprobada.", "ok")
    elif action == "rechazar":
        execute("DELETE FROM escuelas WHERE user_id=?", (user_id,))
        execute("DELETE FROM users WHERE id=?", (user_id,))
        flash("Cuenta eliminada.", "ok")
    else:
        flash("Acción inválida.", "error")
    return redirect(url_for("admin_validar_cuentas"))



@app.route("/forgot", methods=["GET","POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        user = query_one("SELECT * FROM users WHERE email = ? AND role='escuela'", (email,))
        if not user:
            flash("Si existe una cuenta vinculada, se ha enviado un enlace de restablecimiento (simulado).", "ok")
            return redirect(url_for("login"))
        token = generate_token(48)
        expires = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        execute("INSERT INTO password_resets(user_id, token, expires_at, created_at) VALUES (?,?,?,?)",
                (user["id"], token, expires, datetime.utcnow().isoformat()))
        # Show a simulated email page with the reset link (no SMTP required)
        reset_link = url_for("reset_password", token=token, _external=True)
        return render_template("forgot_sent.html", reset_link=reset_link, email=email)
    return render_template("forgot.html")


@app.route("/reset/<token>", methods=["GET","POST"])
def reset_password(token):
    pr = query_one("SELECT * FROM password_resets WHERE token = ?", (token,))
    if not pr:
        flash("Token inválido o expirado.", "error")
        return redirect(url_for("login"))
    # check expiry
    try:
        if datetime.fromisoformat(pr["expires_at"]) < datetime.utcnow():
            flash("Token expirado.", "error")
            return redirect(url_for("login"))
    except Exception:
        pass
    if request.method == "POST":
        pw = request.form.get("password","")
        if not pw or len(pw) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("reset_form.html", token=token)
        execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(pw), pr["user_id"]))
        # delete token
        execute("DELETE FROM password_resets WHERE id = ?", (pr["id"],))
        flash("Contraseña restablecida. Ya puedes iniciar sesión.", "ok")
        return redirect(url_for("login"))
    return render_template("reset_form.html", token=token)



@app.get("/admin/schools")
@login_required
@role_required("admin")
def admin_manage_schools():
    schools = query_all("SELECT u.*, e.id AS escuela_id, e.nombre AS escuela_nombre, e.ciudad FROM users u LEFT JOIN escuelas e ON e.user_id = u.id WHERE u.role='escuela' ORDER BY u.id DESC")
    return render_template("admin_schools.html", schools=schools)

@app.get("/admin/school/<int:escuela_id>/edit")
@login_required
@role_required("admin")
def admin_edit_school_form(escuela_id):
    esc = query_one("SELECT u.*, e.* FROM users u JOIN escuelas e ON e.user_id = u.id WHERE e.id = ?", (escuela_id,))
    if not esc:
        abort(404)
    return render_template("admin_edit_school.html", esc=esc)

@app.post("/admin/school/<int:escuela_id>/edit")
@login_required
@role_required("admin")
def admin_edit_school_submit(escuela_id):
    name = request.form.get("nombre","").strip()
    email = request.form.get("email","").strip().lower()
    ciudad = request.form.get("ciudad","").strip()
    contacto = request.form.get("contacto","").strip()
    telefono = request.form.get("telefono","").strip()
    esc = query_one("SELECT * FROM escuelas WHERE id = ?", (escuela_id,))
    if not esc:
        abort(404)
    # update escuela row
    execute("UPDATE escuelas SET nombre=?, ciudad=?, contacto=?, telefono=? WHERE id=?",
            (name or esc["nombre"], ciudad or esc.get("ciudad",""), contacto or esc.get("contacto",""), telefono or esc.get("telefono",""), escuela_id))
    # update user email/name if changed (ensure unique email)
    other = query_one("SELECT * FROM users WHERE email = ? AND id != ?", (email, esc["user_id"]))
    if other:
        flash("El correo ya está en uso por otra cuenta.", "error")
        return redirect(url_for("admin_edit_school_form", escuela_id=escuela_id))
    execute("UPDATE users SET name=?, email=? WHERE id=?", (name or esc["nombre"], email or esc.get("email",""), esc["user_id"]))
    flash("Datos de la escuela actualizados.", "ok")
    return redirect(url_for("admin_manage_schools"))


@app.post("/admin/school/<int:escuela_id>/toggle")
@login_required
@role_required("admin")
def admin_toggle_school(escuela_id):
    esc = query_one("SELECT u.* FROM users u JOIN escuelas e ON e.user_id = u.id WHERE e.id = ?", (escuela_id,))
    if not esc:
        abort(404)
    new = 0 if esc["is_active"] else 1
    execute("UPDATE users SET is_active=? WHERE id=?", (new, esc["id"]))
    flash("Estado actualizado.", "ok")
    return redirect(url_for("admin_manage_schools"))

@app.post("/admin/school/<int:escuela_id>/delete")
@login_required
@role_required("admin")
def admin_delete_school(escuela_id):
    esc = query_one("SELECT * FROM escuelas WHERE id = ?", (escuela_id,))
    if not esc:
        abort(404)
    execute("DELETE FROM users WHERE id = ?", (esc["user_id"],))
    # cascades should remove escuelas and related pedidos due to FK, but ensure deletion
    execute("DELETE FROM escuelas WHERE id = ?", (escuela_id,))
    flash("Escuela eliminada.", "ok")
    return redirect(url_for("admin_manage_schools"))


if __name__ == "__main__":
    app.run(debug=True)


