
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS pedidos;
DROP TABLE IF EXISTS escuelas;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS paqueterias;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT CHECK(role IN ('admin','vendedora','escuela')) NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE escuelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    ciudad TEXT,
    grado TEXT,
    contacto TEXT,
    telefono TEXT,
    user_id INTEGER UNIQUE NOT NULL,
    vendedora_id INTEGER,
    direccion TEXT,
    colonia TEXT,
    codigo_postal TEXT,
    estado TEXT,
    referencias TEXT,
    dest_nombre TEXT,
    dest_tel TEXT,
    dest_cp TEXT,
    dest_colonia TEXT,
    dest_direccion TEXT,
    dest_correo TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(vendedora_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE paqueterias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    escuela_id INTEGER NOT NULL,
    ciudad TEXT,
    grado TEXT,
    ninas_json TEXT,
    ninos_json TEXT,
    comentario TEXT,
    estado TEXT DEFAULT 'Nuevo',
    paqueteria_id INTEGER,
    created_at TEXT NOT NULL,
    -- nuevos campos globales
    color_calceta_ninas TEXT,
    color_zapato_ninas TEXT,
    color_zapato_ninos TEXT,
    color_monos TEXT,
    color_pantalon TEXT,
    escudos_bordar INTEGER,
    fechas_entrega TEXT, -- JSON list
    entrega TEXT,        -- Ocurre/Domicilio
    FOREIGN KEY(escuela_id) REFERENCES escuelas(id) ON DELETE CASCADE,
    FOREIGN KEY(paqueteria_id) REFERENCES paqueterias(id) ON DELETE SET NULL
);
