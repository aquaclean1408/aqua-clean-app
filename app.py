# ==============================================================================
# SISTEMA DE OPERACIONES AQUA CLEAN - MERIDA (VERSIÓN NUBE / GOOGLE SHEETS)
# Ejecutar en la nube con Streamlit Community Cloud conectado a Google Sheets
# ==============================================================================

import re
import datetime
from urllib.parse import quote

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(
    page_title="Aqua Clean - Sistema de Gestión",
    layout="wide",
    page_icon="🫧",
)

# --- PROTECCIÓN CON CONTRASEÑA ---
def verificar_acceso():
    if st.session_state.get("autenticado", False):
        return True
    st.title("🫧 Acceso Aqua Clean Mérida")
    pwd = st.text_input("Ingresa la contraseña del sistema:", type="password")
    if st.button("Entrar"):
        if "APP_PASSWORD" in st.secrets and pwd == st.secrets["APP_PASSWORD"]:
            st.session_state["autenticado"] = True
            st.rerun()
        elif "APP_PASSWORD" not in st.secrets:
            st.error("Falta configurar APP_PASSWORD en los Secrets de Streamlit.")
        else:
            st.error("Contraseña incorrecta.")
    return False

if not verificar_acceso():
    st.stop()

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

COLUMNAS = [
    "Fecha", "Hora", "Nombre", "Articulo", "Direccion", "Telefono",
    "Precio Final", "Estatus", "Ubicacion_Maps", "Total_Piezas", "Origen",
    "Tiene_Mascotas", "Recordatorio_6_Meses"
]

MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "SETIEMBRE": 9, "SEPT": 9, "SEPT.": 9,
    "SET": 9, "OCTUBRE": 10, "OCT": 10, "NOVIEMBRE": 11,
    "NOV": 11, "DICIEMBRE": 12, "DIC": 12,
}


def traducir_y_limpiar_fecha(valor):
    """Convierte fechas de Google Sheets o textos como '1 AGOSTO 2026' a Timestamp."""
    if pd.isna(valor):
        return pd.NaT

    if isinstance(valor, (pd.Timestamp, datetime.datetime, datetime.date)):
        return pd.to_datetime(valor, errors="coerce")

    texto = str(valor).strip().upper()
    if not texto or texto in {"NAN", "NAT", "HORA", "NONE"} or "TOTAL" in texto:
        return pd.NaT

    texto = re.sub(r"[,_\-]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    tokens = texto.replace(".", "").split()
    if len(tokens) >= 3:
        dia_match = re.search(r"\d{1,2}", tokens[0])
        mes_token = tokens[1].upper()
        anio_match = re.search(r"\d{2,4}", " ".join(tokens[2:]))
        mes = MESES.get(mes_token)
        if dia_match and mes and anio_match:
            dia = int(dia_match.group())
            anio = int(anio_match.group())
            if anio < 100:
                anio += 2000
            try:
                return pd.Timestamp(year=anio, month=mes, day=dia)
            except ValueError:
                return pd.NaT

    # Si viene en formato ISO YYYY-MM-DD
    if re.match(r"^\d{4} \d{2} \d{2}$", texto):
        return pd.to_datetime(texto.replace(" ", "-"), format="%Y-%m-%d", errors="coerce")

    return pd.to_datetime(texto, dayfirst=True, errors="coerce")


def limpiar_telefono(valor):
    if pd.isna(valor):
        return "SIN_TELEFONO"
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    digitos = "".join(c for c in texto if c.isdigit())
    return digitos if len(digitos) >= 10 else "SIN_TELEFONO"


def limpiar_precio(valor):
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).replace("$", "").replace(",", "").strip()
    try:
        return float(texto)
    except (TypeError, ValueError):
        return 0.0


def limpiar_hora(valor):
    if pd.isna(valor):
        return "08:00"
    if isinstance(valor, (datetime.time, pd.Timestamp)):
        return valor.strftime("%H:%M")
    if isinstance(valor, (float, int)) and 0 <= float(valor) < 1:
        minutos = round(float(valor) * 24 * 60)
        return f"{minutos // 60:02d}:{minutos % 60:02d}"
    texto = str(valor).strip()
    match = re.match(r"^(\d{1,2}):(\d{2})", texto)
    if match:
        hora, minuto = int(match.group(1)), int(match.group(2))
        if 0 <= hora <= 23 and 0 <= minuto <= 59:
            return f"{hora:02d}:{minuto:02d}"
    return "08:00"


# ==============================================================================
# FUNCIONES DE LECTURA Y ESCRITURA EN GOOGLE SHEETS
# ==============================================================================

def cargar_vetados():
    """Lee la pestaña Clientes_Vetados de Google Sheets."""
    try:
        df_v = conn.read(worksheet="Clientes_Vetados", ttl=0)
        if df_v is None or df_v.empty or "Telefono" not in df_v.columns:
            return {}
        df_v = df_v.dropna(subset=["Telefono"])
        resultado = {}
        for _, r in df_v.iterrows():
            tel = limpiar_telefono(r["Telefono"])
            if tel != "SIN_TELEFONO":
                resultado[tel] = {
                    "nombre": str(r.get("Nombre", "")).strip(),
                    "motivo": str(r.get("Motivo", "")).strip(),
                    "fecha_registro": str(r.get("Fecha_Registro", "")).strip(),
                }
        return resultado
    except Exception as exc:
        st.warning(f"No se pudo leer la pestaña Clientes_Vetados: {exc}")
        return {}


def guardar_vetados(datos_dict):
    """Guarda los vetos en la pestaña Clientes_Vetados de Google Sheets."""
    filas = [
        {
            "Telefono": str(tel),
            "Nombre": info.get("nombre", ""),
            "Motivo": info.get("motivo", ""),
            "Fecha_Registro": info.get("fecha_registro", ""),
        }
        for tel, info in datos_dict.items()
    ]
    df_out = pd.DataFrame(filas, columns=["Telefono", "Nombre", "Motivo", "Fecha_Registro"])
    conn.update(worksheet="Clientes_Vetados", data=df_out)


def cargar_gastos():
    """Lee la pestaña Gastos_Semanales de Google Sheets."""
    try:
        df_g = conn.read(worksheet="Gastos_Semanales", ttl=0)
        if df_g is None or df_g.empty or "Fecha" not in df_g.columns:
            return []
        df_g = df_g.dropna(subset=["Fecha", "Concepto"])
        gastos = []
        for _, r in df_g.iterrows():
            fecha_str = str(r["Fecha"]).strip()[:10]
            try:
                datetime.date.fromisoformat(fecha_str)
            except ValueError:
                ts = traducir_y_limpiar_fecha(r["Fecha"])
                if pd.isna(ts):
                    continue
                fecha_str = ts.strftime("%Y-%m-%d")
            gastos.append({
                "fecha": fecha_str,
                "concepto": str(r["Concepto"]).strip(),
                "monto": limpiar_precio(r.get("Monto", 0)),
            })
        return gastos
    except Exception as exc:
        st.warning(f"No se pudo leer la pestaña Gastos_Semanales: {exc}")
        return []


def guardar_gastos(lista_gastos):
    """Guarda los gastos en la pestaña Gastos_Semanales de Google Sheets."""
    filas = [
        {"Fecha": g["fecha"], "Concepto": g["concepto"], "Monto": float(g["monto"])}
        for g in lista_gastos
    ]
    df_out = pd.DataFrame(filas, columns=["Fecha", "Concepto", "Monto"])
    conn.update(worksheet="Gastos_Semanales", data=df_out)


def guardar_base(datos):
    """Actualiza la pestaña Base_Unificada en Google Sheets."""
    columnas_salida = [c for c in COLUMNAS if c in datos.columns]
    salida = datos[columnas_salida].copy()
    salida["Fecha"] = pd.to_datetime(salida["Fecha"]).dt.strftime("%Y-%m-%d")
    salida["Telefono"] = salida["Telefono"].astype(str)
    conn.update(worksheet="Base_Unificada", data=salida)


def cargar_datos():
    """Carga la pestaña Base_Unificada desde Google Sheets."""
    try:
        original = conn.read(worksheet="Base_Unificada", ttl=0)
    except Exception as exc:
        st.error(f"No se pudo conectar con la pestaña 'Base_Unificada' en Google Sheets: {exc}")
        return pd.DataFrame(columns=COLUMNAS), 0, 0

    if original is None or original.empty:
        return pd.DataFrame(columns=COLUMNAS), 0, 0

    original.columns = [str(col).strip() for col in original.columns]
    df = original.copy()

    mapa = {}
    for col in df.columns:
        nombre = col.strip().lower()
        if nombre in {"source.name", "source_name", "fecha"}:
            mapa[col] = "Fecha"
        elif nombre == "hora":
            mapa[col] = "Hora"
        elif nombre in {"nombre", "cliente", "nombre cliente"}:
            mapa[col] = "Nombre"
        elif nombre in {"servicio", "articulo", "artículo"}:
            mapa[col] = "Articulo"
        elif nombre in {"direccion", "dirección"}:
            mapa[col] = "Direccion"
        elif nombre in {"telefono", "teléfono", "celular", "móvil", "movil"}:
            mapa[col] = "Telefono"
        elif nombre in {"precio final", "precio_final", "total cobrado"}:
            mapa[col] = "Precio Final"
        elif nombre == "estatus":
            mapa[col] = "Estatus"
        elif nombre == "origen":
            mapa[col] = "Origen"
        elif "maps" in nombre or "ubicacion" in nombre or "ubicación" in nombre:
            mapa[col] = "Ubicacion_Maps"
        elif "piezas" in nombre or "articulos total" in nombre:
            mapa[col] = "Total_Piezas"

    df = df.rename(columns=mapa)

    for col in COLUMNAS:
        if col not in df.columns:
            if col == "Estatus":
                df[col] = "Realizado"
            elif col == "Precio Final":
                df[col] = 0.0
            elif col == "Total_Piezas":
                df[col] = 1
            elif col == "Origen":
                df[col] = "Registro manual"
            else:
                df[col] = ""

    filas_leidas = len(df)
    df["Fecha"] = df["Fecha"].apply(traducir_y_limpiar_fecha)
    fechas_invalidas = int(df["Fecha"].isna().sum())

    df = df[df["Fecha"].notna()].copy()
    df["Hora"] = df["Hora"].apply(limpiar_hora)
    df["Nombre"] = df["Nombre"].fillna("").astype(str).str.strip()
    df["Articulo"] = df["Articulo"].fillna("").astype(str).str.strip()
    df["Direccion"] = df["Direccion"].fillna("").astype(str).str.strip()
    df["Telefono"] = df["Telefono"].apply(limpiar_telefono)
    df["Precio Final"] = df["Precio Final"].apply(limpiar_precio)
    df["Estatus"] = df["Estatus"].fillna("Realizado").astype(str).str.strip()
    df["Ubicacion_Maps"] = df["Ubicacion_Maps"].fillna("").astype(str).str.strip()
    df["Total_Piezas"] = pd.to_numeric(df["Total_Piezas"], errors="coerce").fillna(1)
    df["Origen"] = df["Origen"].fillna("Registro sin origen").astype(str).str.strip()
    df["Tiene_Mascotas"] = df["Tiene_Mascotas"].fillna(False).astype(str).str.casefold().isin(["true", "1", "sí", "si", "yes"])
    df["Recordatorio_6_Meses"] = df["Recordatorio_6_Meses"].fillna(False).astype(str).str.casefold().isin(["true", "1", "sí", "si", "yes"])

    df = df.sort_values(["Fecha", "Hora"]).reset_index(drop=True)
    return df, filas_leidas, fechas_invalidas


# ==============================================================================
# INTERFAZ PRINCIPAL
# ==============================================================================

df_base, filas_leidas, fechas_invalidas = cargar_datos()
clientes_vetados = cargar_vetados()
telefonos_vetados = set(clientes_vetados.keys())

st.title("🫧 Sistema de Operaciones Aqua Clean - Mérida")
st.caption("☁️ Base de datos en vivo: Google Sheets | Tel: 9999099355")

if filas_leidas:
    c1, c2, c3 = st.columns(3)
    c1.metric("Filas leídas de Sheets", f"{filas_leidas:,}")
    c2.metric("Registros con fecha válida", f"{len(df_base):,}")
    c3.metric("Fechas no reconocidas", f"{fechas_invalidas:,}")
    if fechas_invalidas:
        st.warning(
            f"Se encontraron {fechas_invalidas} filas con fecha no reconocida en Google Sheets."
        )

tab_agenda, tab_stats, tab_clientes, tab_alertas = st.tabs([
    "🗓️ Agenda y Registro Diario",
    "📊 Estadísticas e Historial",
    "👥 Buscar / Vetar Clientes",
    "🔔 Alertas de Mantenimiento",
])

horarios_disponibles = [
    f"{h:02d}:{m:02d}"
    for h in range(8, 18)
    for m in (0, 30)
]
horarios_disponibles.append("17:00")

with tab_agenda:
    st.header("Agendar Nuevo Trabajo / Registro Diario")
    col_form, col_cal = st.columns(2)

    with col_form:
        with st.form("registro_servicio", clear_on_submit=True):
            fecha_servicio = st.date_input("Fecha del Servicio", datetime.date.today())
            hora_servicio = st.selectbox("Selecciona la Hora", horarios_disponibles)
            nombre_cliente = st.text_input("Nombre Completo del Cliente").strip()
            articulo_lavar = st.text_input(
                "Artículos a lavar (Ej.: SALA L + COLCHÓN)"
            ).strip().upper()
            total_piezas = st.number_input(
                "Total de artículos incluidos", min_value=1, value=1, step=1
            )
            direccion_cliente = st.text_input("Dirección / Colonia").strip().upper()
            ubicacion_maps = st.text_input("Enlace de Google Maps", placeholder="Pega aquí la ubicación que envíe el cliente").strip()
            tiene_mascotas = st.checkbox("¿El cliente tiene mascotas?")
            recordatorio_6_meses = st.checkbox("Programar recordatorio especial de limpieza en 6 meses")
            telefono_cliente = st.text_input("Teléfono (10 dígitos)").strip()
            precio_final = st.number_input(
                "Cobro total final ($ MXN)", min_value=0.0, step=50.0
            )
            estatus_inicial = st.selectbox(
                "Estatus inicial", ["Realizado", "Pendiente", "Reagendado", "Cancelado"]
            )
            guardar = st.form_submit_button("💾 Guardar y agendar")

            if guardar:
                tel_limpio = limpiar_telefono(telefono_cliente)
                if not nombre_cliente or tel_limpio == "SIN_TELEFONO":
                    st.error("El nombre y un teléfono válido son obligatorios.")
                else:
                    nueva_fila = pd.DataFrame([{
                        "Fecha": pd.Timestamp(fecha_servicio),
                        "Hora": hora_servicio,
                        "Nombre": nombre_cliente,
                        "Articulo": articulo_lavar,
                        "Direccion": direccion_cliente,
                        "Telefono": tel_limpio,
                        "Precio Final": precio_final,
                        "Estatus": estatus_inicial,
                        "Ubicacion_Maps": ubicacion_maps,
                        "Total_Piezas": total_piezas,
                        "Origen": "Registro manual",
                        "Tiene_Mascotas": tiene_mascotas,
                        "Recordatorio_6_Meses": recordatorio_6_meses,
                    }])
                    salida = pd.concat([df_base[COLUMNAS], nueva_fila], ignore_index=True)
                    try:
                        guardar_base(salida)
                        st.success("Cita guardada correctamente en Google Sheets.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo guardar en Google Sheets: {exc}")

    with col_cal:
        st.subheader("📅 Agenda del día")
        fecha_ver = st.date_input("Ver agenda del día", datetime.date.today(), key="fecha_agenda")
        df_dia = df_base[df_base["Fecha"].dt.date == fecha_ver].copy() if not df_base.empty else pd.DataFrame(columns=COLUMNAS)
        st.subheader("Disponibilidad para informar al cliente")
        ocupadas = set(df_dia.loc[df_dia["Estatus"].astype(str).str.casefold() != "cancelado", "Hora"].astype(str))
        disponibilidad = pd.DataFrame({
            "Hora": horarios_disponibles,
            "Disponibilidad": ["🔴 OCUPADO" if h in ocupadas else "🟢 DISPONIBLE" for h in horarios_disponibles]
        })
        st.dataframe(
            disponibilidad.style.apply(
                lambda fila: [
                    "background-color: #ffd6d6; color: #8b0000; font-weight: bold;" if "OCUPADO" in fila["Disponibilidad"]
                    else "background-color: #d8f3dc; color: #14532d; font-weight: bold;"
                ] * len(fila), axis=1
            ),
            use_container_width=True, hide_index=True
        )
        if not df_base.empty:
            df_dia_activo = df_dia[df_dia["Estatus"].str.casefold() != "cancelado"].copy()
            st.metric("Artículos programados", int(df_dia_activo["Total_Piezas"].sum()))
            st.metric("Venta estimada", f"${df_dia_activo['Precio Final'].sum():,.2f} MXN")

            if not df_dia_activo.empty:
                st.subheader("Reporte de ruta")
                lineas = [
                    f"*🫧 AGENDA AQUA CLEAN - {fecha_ver.strftime('%d/%m/%Y')}*"
                ]
                for _, fila in df_dia_activo.sort_values("Hora").iterrows():
                    lineas.append(
                        f"\n⏰ *HORA:* {fila['Hora']}\n"
                        f"👤 *CLIENTE:* {fila['Nombre']}\n"
                        f"🛋️ *SERVICIO:* {fila['Articulo']}\n"
                        f"📍 *DIRECCIÓN:* {fila['Direccion']}\n"
                        f"📞 *TEL:* {fila['Telefono']}\n"
                        f"💵 *A COBRAR:* ${fila['Precio Final']:,.2f} MXN"
                    )
                    if bool(fila.get("Tiene_Mascotas", False)):
                        lineas.append("🐾 *TIENE MASCOTAS:* Sí")
                    if fila["Ubicacion_Maps"]:
                        lineas.append(f"🗺️ *MAPS:* {fila['Ubicacion_Maps']}")
                st.text_area("Copia y pega en WhatsApp", "\n".join(lineas), height=260)

            st.subheader("Desglose de citas por hora")
            st.caption("Puedes editar una cita, cambiar su estado o eliminar registros duplicados. Los cambios se guardan en Google Sheets.")
            if df_dia.empty:
                st.info("No hay citas registradas para esta fecha.")
            else:
                for idx, fila in df_dia.sort_values(["Hora", "Nombre"]).iterrows():
                    estado = str(fila["Estatus"]).strip().casefold()
                    emoji = {"realizado": "🟢", "pendiente": "🟡", "cancelado": "🔴", "reagendado": "🔵"}.get(estado, "🟡")
                    with st.expander(f"{emoji} {fila['Hora']} — {fila['Nombre']} — {fila['Estatus']}"):
                        st.write(f"Servicio: {fila['Articulo']} ({fila['Total_Piezas']} pzs)")
                        st.write(f"Dirección: {fila['Direccion']}")
                        st.write(f"Teléfono: {fila['Telefono']}")
                        st.write(f"Google Maps: {fila['Ubicacion_Maps'] or 'Sin enlace registrado'}")
                        st.write(f"Tiene mascotas: {'Sí 🐾' if bool(fila['Tiene_Mascotas']) else 'No'}")
                        st.write(f"Recordatorio especial 6 meses: {'Sí ⭐' if bool(fila['Recordatorio_6_Meses']) else 'No'}")
                        st.write(f"Total: ${fila['Precio Final']:,.2f}")
                        with st.form(f"editar_cita_{idx}"):
                            e_fecha = st.date_input("Fecha", value=fila["Fecha"].date(), key=f"ef_{idx}")
                            horas_edicion = sorted(set(horarios_disponibles + [str(fila["Hora"])]))
                            hora_actual = str(fila["Hora"])
                            e_hora = st.selectbox("Hora", horas_edicion, index=horas_edicion.index(hora_actual) if hora_actual in horas_edicion else 0, key=f"eh_{idx}")
                            e_nombre = st.text_input("Cliente", value=str(fila["Nombre"]), key=f"en_{idx}")
                            e_telefono = st.text_input("Teléfono", value=str(fila["Telefono"]), key=f"et_{idx}")
                            e_servicio = st.text_input("Servicio", value=str(fila["Articulo"]), key=f"es_{idx}")
                            e_direccion = st.text_input("Dirección", value=str(fila["Direccion"]), key=f"ed_{idx}")
                            e_maps = st.text_input("Enlace de Google Maps", value=str(fila["Ubicacion_Maps"]), key=f"emaps_{idx}")
                            e_mascotas = st.checkbox("¿Tiene mascotas?", value=bool(fila["Tiene_Mascotas"]), key=f"emasc_{idx}")
                            e_recordatorio = st.checkbox("Recordatorio especial en 6 meses", value=bool(fila["Recordatorio_6_Meses"]), key=f"erec_{idx}")
                            e_precio = st.number_input("Importe ($ MXN)", min_value=0.0, value=float(fila["Precio Final"]), step=50.0, key=f"ep_{idx}")
                            e_piezas = st.number_input("Artículos", min_value=1, value=max(1, int(fila["Total_Piezas"])), step=1, key=f"epi_{idx}")
                            estados = ["Pendiente", "Realizado", "Cancelado", "Reagendado"]
                            estado_actual = str(fila["Estatus"]).title()
                            if estado_actual not in estados:
                                estado_actual = "Pendiente"
                            e_estado = st.selectbox("Estado", estados, index=estados.index(estado_actual), key=f"ee_{idx}")
                            guardar_edicion = st.form_submit_button("💾 Guardar cambios")
                        col_guardar, col_eliminar = st.columns(2)
                        if guardar_edicion:
                            if not e_nombre.strip():
                                st.error("El nombre del cliente no puede quedar vacío.")
                            elif limpiar_telefono(e_telefono) == "SIN_TELEFONO":
                                st.error("Ingresa un teléfono válido de al menos 10 dígitos.")
                            else:
                                df_base.loc[idx, "Fecha"] = pd.Timestamp(e_fecha)
                                df_base.loc[idx, "Hora"] = e_hora
                                df_base.loc[idx, "Nombre"] = e_nombre.strip()
                                df_base.loc[idx, "Telefono"] = limpiar_telefono(e_telefono)
                                df_base.loc[idx, "Articulo"] = e_servicio.strip()
                                df_base.loc[idx, "Direccion"] = e_direccion.strip()
                                df_base.loc[idx, "Ubicacion_Maps"] = e_maps.strip()
                                df_base.loc[idx, "Tiene_Mascotas"] = e_mascotas
                                df_base.loc[idx, "Recordatorio_6_Meses"] = e_recordatorio
                                df_base.loc[idx, "Precio Final"] = float(e_precio)
                                df_base.loc[idx, "Total_Piezas"] = int(e_piezas)
                                df_base.loc[idx, "Estatus"] = e_estado
                                try:
                                    guardar_base(df_base.sort_values(["Fecha", "Hora"]))
                                    st.success("Cita actualizada y guardada en Google Sheets.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"No se pudo guardar el cambio: {exc}")
                        with col_eliminar:
                            if st.button("🗑️ Eliminar cita", key=f"eliminar_{idx}"):
                                st.session_state[f"confirmar_eliminar_{idx}"] = True
                        if st.session_state.get(f"confirmar_eliminar_{idx}", False):
                            st.warning("Esta acción elimina el registro seleccionado de Google Sheets.")
                            if st.button("Confirmar eliminación", key=f"confirmar_eliminar_boton_{idx}"):
                                df_base = df_base.drop(index=idx).reset_index(drop=True)
                                try:
                                    guardar_base(df_base)
                                    st.session_state.pop(f"confirmar_eliminar_{idx}", None)
                                    st.success("Cita eliminada.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"No se pudo eliminar la cita: {exc}")
        else:
            st.info("No hay registros con fechas válidas para mostrar.")

with tab_stats:
    st.header("📊 Resumen diario y semanal de ventas")
    if not df_base.empty:
        df_ventas = df_base.copy()
        df_ventas["Estado_normalizado"] = df_ventas["Estatus"].astype(str).str.strip().str.casefold()
        hoy_ventas = datetime.date.today()
        fecha_resumen = st.date_input("Fecha para el resumen diario", hoy_ventas, key="fecha_resumen_ventas")
        inicio_semana = fecha_resumen - datetime.timedelta(days=fecha_resumen.weekday())
        fin_semana = inicio_semana + datetime.timedelta(days=6)
        realizados_dia = df_ventas[(df_ventas["Fecha"].dt.date == fecha_resumen) & (df_ventas["Estado_normalizado"] == "realizado")]
        semana = df_ventas[(df_ventas["Fecha"].dt.date >= inicio_semana) & (df_ventas["Fecha"].dt.date <= fin_semana)]
        realizados_semana = semana[semana["Estado_normalizado"] == "realizado"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Venta realizada del día", f"${realizados_dia['Precio Final'].sum():,.2f} MXN")
        c2.metric("Servicios realizados hoy", len(realizados_dia))
        c3.metric("Citas en agenda del día", len(df_ventas[df_ventas["Fecha"].dt.date == fecha_resumen]))
        c4, c5, c6 = st.columns(3)
        c4.metric("Venta realizada semanal", f"${realizados_semana['Precio Final'].sum():,.2f} MXN")
        c5.metric("Servicios realizados semana", len(realizados_semana))
        c6.metric("Semana", f"{inicio_semana.strftime('%d/%m')}–{fin_semana.strftime('%d/%m/%Y')}")
        conteos = semana["Estado_normalizado"].value_counts()
        c7, c8, c9, c10 = st.columns(4)
        c7.metric("Pendientes", int(conteos.get("pendiente", 0)))
        c8.metric("Cancelados", int(conteos.get("cancelado", 0)))
        c9.metric("Reagendados", int(conteos.get("reagendado", 0)))
        c10.metric("Realizados", int(conteos.get("realizado", 0)))
        st.divider()

    st.header("💸 Gastos de la semana")
    gastos = cargar_gastos()
    with st.form("form_gastos_semanales", clear_on_submit=True):
        fecha_gasto = st.date_input("Fecha del gasto", datetime.date.today(), key="fecha_gasto")
        concepto_gasto = st.text_input("Concepto del gasto", placeholder="Gasolina, productos, comida, etc.")
        monto_gasto = st.number_input("Importe ($ MXN)", min_value=0.0, step=10.0)
        guardar_gasto = st.form_submit_button("➕ Registrar gasto")
    if guardar_gasto:
        if not concepto_gasto.strip() or monto_gasto <= 0:
            st.error("Indica el concepto y un importe mayor a cero.")
        else:
            gastos.append({"fecha": fecha_gasto.isoformat(), "concepto": concepto_gasto.strip(), "monto": float(monto_gasto)})
            try:
                guardar_gastos(gastos)
                st.success("Gasto registrado en Google Sheets.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo guardar el gasto: {exc}")

    fecha_gastos = st.date_input("Semana de gastos a consultar", datetime.date.today(), key="semana_gastos")
    inicio_gastos = fecha_gastos - datetime.timedelta(days=fecha_gastos.weekday())
    fin_gastos = inicio_gastos + datetime.timedelta(days=6)
    gastos_semana = [g for g in gastos if inicio_gastos <= datetime.date.fromisoformat(g["fecha"]) <= fin_gastos]
    total_gastos = sum(float(g.get("monto", 0)) for g in gastos_semana)
    venta_semana = 0.0
    if not df_base.empty:
        venta_semana = df_base[
            (df_base["Fecha"].dt.date >= inicio_gastos)
            & (df_base["Fecha"].dt.date <= fin_gastos)
            & (df_base["Estatus"].astype(str).str.casefold() == "realizado")
        ]["Precio Final"].sum()
    cg1, cg2, cg3 = st.columns(3)
    cg1.metric("Gastos de la semana", f"${total_gastos:,.2f} MXN")
    cg2.metric("Ventas realizadas", f"${venta_semana:,.2f} MXN")
    cg3.metric("Diferencia ventas - gastos", f"${venta_semana-total_gastos:,.2f} MXN")
    if gastos_semana:
        st.dataframe(pd.DataFrame(gastos_semana), use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no hay gastos registrados en esta semana.")

    st.header("Historial de clientes y frecuencia")
    if df_base.empty:
        st.info("No hay registros disponibles.")
    else:
        validos = df_base[
            (df_base["Estatus"].str.strip().str.casefold() == "realizado")
            & (df_base["Telefono"] != "SIN_TELEFONO")
        ].copy()
        if validos.empty:
            st.info("No hay registros con teléfono válido.")
        else:
            visitas = validos.groupby("Telefono").agg(
                Nombre=("Nombre", "last"),
                Total_Visitas=("Telefono", "size"),
                Ultima_Fecha=("Fecha", "max"),
                Historial_Servicios=("Articulo", lambda x: " | ".join(
                    dict.fromkeys(str(v) for v in x if str(v).strip() and str(v).lower() != "nan")
                )),
            ).reset_index()
            frecuentes = visitas[visitas["Total_Visitas"] >= 2].sort_values(
                "Total_Visitas", ascending=False
            )
            st.metric("Clientes frecuentes (2+ servicios)", len(frecuentes))
            st.dataframe(
                frecuentes[["Nombre", "Telefono", "Total_Visitas", "Historial_Servicios", "Ultima_Fecha"]],
                use_container_width=True,
            )

with tab_clientes:
    st.header("👥 Buscar, consultar, vetar o eliminar clientes")
    st.caption(
        "Los clientes vetados se conservan en el historial, aparecen marcados en rojo "
        "y quedan excluidos de las alertas y del envío de mensajes de mantenimiento."
    )

    if df_base.empty:
        st.info("No hay registros disponibles para buscar.")
    else:
        clientes = df_base[df_base["Telefono"] != "SIN_TELEFONO"].copy()
        if clientes.empty:
            st.info("No hay clientes con teléfono válido para buscar.")
        else:
            resumen = clientes.sort_values(["Fecha", "Hora"]).groupby("Telefono", as_index=False).agg(
                Nombre=("Nombre", "last"),
                Direccion=("Direccion", "last"),
                Ultima_Fecha=("Fecha", "max"),
                Servicios=("Telefono", "size"),
            )
            resumen["Estado"] = resumen["Telefono"].apply(
                lambda t: "🔴 VETADO" if t in telefonos_vetados else "🟢 ACTIVO"
            )

            busqueda = st.text_input(
                "Buscar por nombre o teléfono", placeholder="Escribe el nombre o número..."
            ).strip().casefold()
            filtrados = resumen[
                resumen["Nombre"].astype(str).str.casefold().str.contains(busqueda, na=False)
                | resumen["Telefono"].astype(str).str.contains(busqueda, na=False)
            ].copy()

            st.metric("Clientes encontrados", len(filtrados))
            if not filtrados.empty:
                tabla = filtrados.copy()
                tabla["Ultima_Fecha"] = tabla["Ultima_Fecha"].dt.strftime("%d/%m/%Y")
                def pintar_vetados(fila):
                    color = "background-color: #ffd6d6; color: #8b0000; font-weight: bold;" if fila["Telefono"] in telefonos_vetados else ""
                    return [color] * len(fila)
                st.dataframe(
                    tabla[["Estado", "Nombre", "Telefono", "Direccion", "Servicios", "Ultima_Fecha"]].style.apply(pintar_vetados, axis=1),
                    use_container_width=True,
                    hide_index=True,
                )

                opciones_clientes = {
                    f"{r['Nombre']} — {r['Telefono']} {'🔴 VETADO' if r['Telefono'] in telefonos_vetados else ''}": r['Telefono']
                    for _, r in filtrados.iterrows()
                }
                elegido = st.selectbox("Selecciona el cliente para cambiar su estado", list(opciones_clientes.keys()))
                telefono_elegido = opciones_clientes[elegido]
                registro_elegido = resumen[resumen["Telefono"] == telefono_elegido].iloc[0]
                esta_vetado = telefono_elegido in telefonos_vetados
                if esta_vetado:
                    st.error(f"🔴 {registro_elegido['Nombre']} está VETADO. No aparecerá en las alertas ni se habilitará el mensaje de mantenimiento.")
                    motivo_actual = str(clientes_vetados.get(telefono_elegido, {}).get("motivo", ""))
                else:
                    st.success(f"🟢 {registro_elegido['Nombre']} está activo.")
                    motivo_actual = ""

                with st.form("form_estado_cliente"):
                    motivo = st.text_area(
                        "Motivo del veto (opcional)",
                        value=motivo_actual,
                        placeholder="Ej. mal trato, incumplimiento de pago, conducta inapropiada...",
                    )
                    if esta_vetado:
                        accion = st.radio("Acción", ["Mantener vetado", "Quitar veto y activar"], horizontal=True)
                    else:
                        accion = st.radio("Acción", ["Mantener activo", "Vetar cliente"], horizontal=True)
                    guardar_estado = st.form_submit_button("💾 Guardar estado del cliente")

                if guardar_estado:
                    nuevos_vetados = dict(clientes_vetados)
                    if accion == "Vetar cliente":
                        nuevos_vetados[telefono_elegido] = {
                            "nombre": str(registro_elegido["Nombre"]),
                            "motivo": motivo.strip(),
                            "fecha_registro": datetime.date.today().isoformat(),
                        }
                        guardar_vetados(nuevos_vetados)
                        st.success("Cliente vetado. Se conserva su historial y no recibirá alertas de mantenimiento.")
                        st.rerun()
                    elif accion == "Quitar veto y activar":
                        nuevos_vetados.pop(telefono_elegido, None)
                        guardar_vetados(nuevos_vetados)
                        st.success("Veto retirado. El cliente vuelve a ser elegible para alertas.")
                        st.rerun()
                    elif accion == "Mantener vetado":
                        nuevos_vetados[telefono_elegido] = {
                            "nombre": str(registro_elegido["Nombre"]),
                            "motivo": motivo.strip(),
                            "fecha_registro": clientes_vetados.get(telefono_elegido, {}).get("fecha_registro", datetime.date.today().isoformat()),
                        }
                        guardar_vetados(nuevos_vetados)
                        st.success("Información del veto actualizada.")
                        st.rerun()
                    else:
                        st.info("El cliente permanece activo; no se hicieron cambios.")

                st.divider()
                st.subheader("🗑️ Eliminar cliente de la base de datos")
                st.warning("Esta acción elimina permanentemente todos los servicios e historial asociados a este teléfono. Si solo deseas evitar mensajes, utiliza la opción Vetar cliente.")
                confirmar_cliente = st.checkbox(
                    f"Confirmo que deseo eliminar a {registro_elegido['Nombre']} ({telefono_elegido}) y todo su historial",
                    key=f"confirmar_cliente_{telefono_elegido}"
                )
                if st.button("Eliminar cliente y todo su historial", key=f"borrar_cliente_{telefono_elegido}", disabled=not confirmar_cliente):
                    base_actualizada = df_base[df_base["Telefono"] != telefono_elegido].copy()
                    nuevos_vetados = dict(clientes_vetados)
                    nuevos_vetados.pop(telefono_elegido, None)
                    try:
                        guardar_base(base_actualizada)
                        guardar_vetados(nuevos_vetados)
                        st.success("Cliente e historial eliminados.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo eliminar el cliente: {exc}")
            else:
                st.info("No hay clientes que coincidan con la búsqueda.")

with tab_alertas:
    st.header("🔔 Alertas de mantenimiento preventivo")
    st.caption(
        "Se considera la última visita válida de cada teléfono, se excluyen citas canceladas y clientes vetados."
    )

    if df_base.empty:
        st.warning("No hay registros con fechas válidas.")
    else:
        validos = df_base[
            (df_base["Estatus"].str.strip().str.casefold() == "realizado")
            & (df_base["Telefono"] != "SIN_TELEFONO")
            & (df_base["Nombre"].str.strip() != "")
            & (~df_base["Telefono"].isin(telefonos_vetados))
        ].copy()

        if validos.empty:
            st.info("No hay registros con teléfono y nombre válidos para generar alertas.")
        else:
            meses_filtro = st.slider(
                "Plazo de mantenimiento (solo clientes cuya fecha objetivo cae dentro de ±7 días)",
                min_value=1, max_value=60, value=6
            )
            fecha_actual = datetime.date.today()
            fecha_actual_ts = pd.Timestamp(fecha_actual)

            validos = validos.sort_values(["Fecha", "Hora"])
            ultimas_filas = validos.groupby("Telefono", as_index=False).tail(1).copy()
            ultimas_filas = ultimas_filas.rename(columns={
                "Fecha": "Ultima_Fecha",
                "Articulo": "Ultimo_Articulo",
            })
            ultimas_filas["Dias_Desde_Ultimo"] = (
                fecha_actual_ts - ultimas_filas["Ultima_Fecha"]
            ).dt.days
            ultimas_filas = ultimas_filas[ultimas_filas["Dias_Desde_Ultimo"] >= 0].copy()
            ultimas_filas["Meses_Desde_Ultimo"] = (
                ultimas_filas["Dias_Desde_Ultimo"] / 30.4375
            ).round(1)

            fecha_objetivo = fecha_actual_ts - pd.DateOffset(months=int(meses_filtro))
            inicio_ventana = fecha_objetivo - pd.Timedelta(days=7)
            fin_ventana = fecha_objetivo + pd.Timedelta(days=7)

            alertas = ultimas_filas[
                (ultimas_filas["Ultima_Fecha"] >= inicio_ventana)
                & (ultimas_filas["Ultima_Fecha"] <= fin_ventana)
            ].copy()
            alertas = alertas.sort_values("Ultima_Fecha")
            st.caption(
                f"Ventana para {meses_filtro} meses: del "
                f"{inicio_ventana.strftime('%d/%m/%Y')} al "
                f"{fin_ventana.strftime('%d/%m/%Y')} (7 días antes y después)."
            )

            if alertas.empty:
                st.info(
                    f"No hay clientes cuya última visita esté dentro de la ventana de 7 días "
                    f"para el plazo de {meses_filtro} meses."
                )
            else:
                st.write(f"### {len(alertas)} clientes para seguimiento")
                mostrar = alertas[[
                    "Nombre", "Telefono", "Direccion", "Ultimo_Articulo",
                    "Ultima_Fecha", "Meses_Desde_Ultimo"
                ]].copy()
                mostrar["Ultima_Fecha"] = mostrar["Ultima_Fecha"].dt.strftime("%d/%m/%Y")
                st.dataframe(mostrar, use_container_width=True)

                opciones = {
                    f"{r['Nombre']} — {r['Telefono']}": idx
                    for idx, r in alertas.iterrows()
                }
                cliente_opcion = st.selectbox(
                    "Selecciona un cliente para preparar el mensaje",
                    list(opciones.keys())
                )
                fila = alertas.loc[opciones[cliente_opcion]]
                nombre = str(fila["Nombre"])
                telefono = str(fila["Telefono"])
                articulo = str(fila["Ultimo_Articulo"])
                mensaje = (
                    f"Hola {nombre}, te saluda el equipo de Aqua Clean 🫧. "
                    f"Te contactamos para dar seguimiento al servicio de {articulo} "
                    f"que realizamos el {fila['Ultima_Fecha'].strftime('%d/%m/%Y')}. "
                    "¿Te gustaría agendar un mantenimiento?"
                )
                st.text_area("Mensaje personalizado", mensaje, height=120)
                enlace = f"https://wa.me/{telefono}?text={quote(mensaje)}"
                st.link_button("📲 Abrir conversación en WhatsApp", enlace)

        st.divider()
        st.subheader("⭐ Recordatorios especiales solicitados por el cliente")
        if "Recordatorio_6_Meses" in df_base.columns:
            especiales = df_base[
                (df_base["Estatus"].astype(str).str.casefold() == "realizado")
                & (df_base["Recordatorio_6_Meses"] == True)
                & (df_base["Telefono"] != "SIN_TELEFONO")
                & (~df_base["Telefono"].isin(telefonos_vetados))
            ].sort_values(["Fecha", "Hora"]).groupby("Telefono", as_index=False).tail(1).copy()
            if not especiales.empty:
                especiales["Fecha_Recordatorio"] = especiales["Fecha"] + pd.DateOffset(months=6)
                hoy_ts = pd.Timestamp(datetime.date.today())
                especiales = especiales[
                    (especiales["Fecha_Recordatorio"] >= hoy_ts - pd.Timedelta(days=7))
                    & (especiales["Fecha_Recordatorio"] <= hoy_ts + pd.Timedelta(days=7))
                ]
            if especiales.empty:
                st.info("No hay recordatorios especiales de 6 meses próximos.")
            else:
                for _, especial in especiales.iterrows():
                    fecha_rec = especial["Fecha_Recordatorio"].strftime("%d/%m/%Y")
                    st.write(f"**{especial['Nombre']}** — {especial['Telefono']} — limpieza solicitada para {fecha_rec}")
                    texto = (
                        f"Hola {especial['Nombre']}, te saluda Aqua Clean 🫧. "
                        f"Nos pediste recordarte tu limpieza aproximadamente 6 meses después de tu servicio del "
                        f"{especial['Fecha'].strftime('%d/%m/%Y')}. ¿Te gustaría agendar?"
                    )
                    st.text_area("Mensaje especial", texto, key=f"mensaje_especial_{especial['Telefono']}", height=90)
                    st.link_button(
                        "📲 Contactar por WhatsApp",
                        f"https://wa.me/{especial['Telefono']}?text={quote(texto)}",
                        key=f"wa_especial_{especial['Telefono']}"
                    )
