# Instal·lació de les llibreries necessàries
from selenium import webdriver
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from urllib import robotparser
from datetime import datetime
import random
import time
import os
import csv
import re

current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
capture_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# User-Agent identificatiu que s'enviarà al servidor
USER_AGENT = "AcademicUOC"


# ---------------------------------------------------------------------------
# Bon ús del web scraping
# ---------------------------------------------------------------------------

# Funció per verificar el fitxer robots.txt
def get_robot_txt(url):
    if url.endswith('/'):
        path = url
    else:
        path = url + '/'

    try:
        request = requests.get(path + "robots.txt", headers={"User-Agent": USER_AGENT}, timeout=10)
        request.raise_for_status()
        return request.text
    except Exception as e:
        print(f"No s'ha pogut llegir robots.txt: {e}")
        return None


# Pausa aleatòria entre peticions per no saturar el servidor
def pausa(min_s=2, max_s=4):
    time.sleep(random.uniform(min_s, max_s))


# Funció que carrega una pàgina aplicant les bones pràctiques:
#  1. Comprova que el robots.txt permet visitar la URL
#  2. Espera que aparegui el contingut (en lloc d'un temps fix)
#  3. Reintenta fins a 3 vegades si hi ha errors, esperant cada cop més (5, 10, 20 s)
#  4. Fa una pausa aleatòria després de cada petició
def carregar_pagina(url, selector_espera=None, intents=3):
    if not robots.can_fetch(USER_AGENT, url):
        print(f"  [robots.txt] Ruta no permesa, s'omet: {url}")
        return False

    for intent in range(1, intents + 1):
        try:
            browser.get(url)
            if selector_espera:
                WebDriverWait(browser, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector_espera)))
            pausa()
            return True
        except (TimeoutException, WebDriverException) as e:
            espera = 5 * 2 ** (intent - 1)
            print(f"  Error carregant {url} (intent {intent}/{intents}): {type(e).__name__}. "
                  f"Es torna a provar en {espera} s.")
            time.sleep(espera)

    print(f"  No s'ha pogut carregar: {url}")
    return False


# Lloc web objectiu
URL = "https://crtm.es/"
robots_text = get_robot_txt(URL)
print(robots_text)

# Es carreguen les regles del robots.txt per poder-les consultar abans de cada petició
robots = robotparser.RobotFileParser()
if robots_text:
    robots.parse(robots_text.splitlines())

# Configuració bàsica
option = Options()
option.add_argument("--headless=new")
option.add_argument("--incognito")
option.add_argument(f"user-agent={USER_AGENT}")

# Inicialitzar navegador
browser = webdriver.Chrome(options=option)
browser.set_page_load_timeout(30)  # si una pàgina triga més de 30 s es considera un error

# Comprovació del User-Agent real que envia el navegador
print("User-Agent utilitzat:", browser.execute_script("return navigator.userAgent"))

# Estructura per guardar la informació de les línies per categoria de transport
all_lines_info = []

transport_line_type = lambda title: (
    "Cercanías" if "cercanías" in title.lower()
    else "Metro Ligero" if "metro ligero" in title.lower()
    else "Metro"
)

# Diccionari per emmagatzemar i classificar les incidències recollides segons el seu tipus de transport
notices_by_category = {"Metro": [], "Metro Ligero": [], "Cercanías": []}

# El bloc try/finally garanteix que el navegador es tanca encara que hi hagi un error
try:

    # Extracció de línies i parades de transports
    transport_sections = [
        {"type": "Metro", "selector_titulo": "a[title='Metro']"},
        {"type": "Metro Ligero / Tranvía", "selector_titulo": "a[title='Metro Ligero / Tranvía']"},
        {"type": "Cercanías", "selector_titulo": "a[title*='Cercanías']"}
    ]

    if carregar_pagina("https://crtm.es/tu-transporte-publico/", "div.modMosaico"):

        # Primer es recullen les URLs dels llistats de línies de totes les seccions.
        # Així no cal tornar enrere (browser.back()) a la pàgina inicial, cosa que
        # suposaria peticions innecessàries al servidor.
        for item in transport_sections:
            try:
                # Localització de l'element principal del transport actual i el seu bloc contenidor
                main_link = browser.find_element(By.CSS_SELECTOR, f"div.modMosaico h3.titu8 {item['selector_titulo']}")
                block = main_link.find_element(By.XPATH, "./ancestor::div[@class='modMosaico']")
                # Cerquem l'enllaç específic que de la llista de línies d'aquest transport
                link_lines = block.find_element(By.CSS_SELECTOR, "ul li a[title*='Línea'], ul li a[title*='línea']")
                item["url_lines"] = link_lines.get_attribute("href")
            except Exception as e:
                print(f"No s'ha trobat el llistat de línies de {item['type']}: {e}")

    for item in transport_sections:
        url_lines = item.get("url_lines")
        if not url_lines:
            continue

        print(f"\n▶ Processant secció: {item['type']}")
        try:
            # Navegació cap a la pàgina de línies d'aquesta secció
            if not carregar_pagina(url_lines, "div.listaBotones"):
                continue

            extracted_lines = []
            # Obtenció de tots els elements que corresponen a cada línia individual
            line_elements = browser.find_elements(By.CSS_SELECTOR, "div.listaBotones ul li a")

            for a_elem in line_elements:
                line_title_raw = a_elem.get_attribute("title")
                line_url = a_elem.get_attribute("href")

                if line_url and line_title_raw:
                    # Eliminació de sufixos innecessaris per deixar només el nom de la línia, per posteriorment utilitzar-lo per la recerca d'incidències
                    line_title_clean = line_title_raw
                    for suffix in [" de Metro Ligero", " de Metro", " de Cercanías", " de Cercanias"]:
                        line_title_clean = line_title_clean.replace(suffix, "")
                    line_title_clean = line_title_clean.strip()

                    # Es desa la informació bàsica de la línia a la llista temporal
                    extracted_lines.append({
                        "raw_title": line_title_raw,
                        "clean_title": line_title_clean,
                        "url": line_url
                    })

            print(f"  {len(extracted_lines)} línies trobades")

            # S'accedeix individualment a l'URL de cada línia per extreure'n les parades
            for i, line in enumerate(extracted_lines, 1):
                print(f"  [{i}/{len(extracted_lines)}] {line['clean_title']}")
                if not carregar_pagina(line["url"], "table.tablaParadas"):
                    continue

                stop_names = []
                try:
                    # Selecció de l'enllaç que va immediatament després de la icona 'ico' dins de la primera cel·la de la fila
                    stop_elements = browser.find_elements(By.CSS_SELECTOR, "table.tablaParadas tr td:first-child span.ico ~ a")
                    for elem in stop_elements:
                        name = elem.get_attribute("textContent").strip()
                        # Filtració de textos de servei o enllaços buits
                        if name and not name.startswith("Enlace a la información"):
                            stop_names.append(name)

                    # Informació addicional de cada estació a partir de les icones de la taula
                    # (el text alternatiu "alt" de cada imatge descriu el servei)
                    accessible_stops = 0
                    correspondence_stops = 0
                    parking_stops = 0
                    zones = []
                    rows = browser.find_elements(By.CSS_SELECTOR, "table.tablaParadas tr")
                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        # Només es tenen en compte les files que corresponen a una estació
                        if len(cells) < 2 or not cells[0].find_elements(By.CSS_SELECTOR, "span.ico ~ a"):
                            continue
                        # 1a cel·la: icona de l'estació (indica si té correspondència)
                        station_icons = [(img.get_attribute("alt") or "").lower()
                                         for img in cells[0].find_elements(By.TAG_NAME, "img")]
                        # 2a cel·la: icones de serveis (zona tarifària, accessibilitat, aparcament...)
                        service_icons = [(img.get_attribute("alt") or "")
                                         for img in cells[1].find_elements(By.TAG_NAME, "img")]

                        if any("correspondencia" in alt for alt in station_icons):
                            correspondence_stops += 1
                        if any("accesible" in alt.lower() for alt in service_icons):
                            accessible_stops += 1
                        if any("aparcamiento" in alt.lower() for alt in service_icons):
                            parking_stops += 1
                        for alt in service_icons:
                            if alt.startswith("Zona tarifaria"):
                                zone = alt.replace("Zona tarifaria", "").strip()
                                if zone not in zones:
                                    zones.append(zone)

                    # Càlculs bàsics dels paràmetres
                    total_stops = len(stop_names)
                    first_stop = stop_names[0] if total_stops > 0 else "N/A"
                    last_stop = stop_names[-1] if total_stops > 0 else "N/A"
                    all_stops_str = ", ".join(stop_names) if total_stops > 0 else "N/A"
                    zones_str = "|".join(zones) if zones else "N/A"
                    accessible_pct = round(accessible_stops / total_stops * 100, 1) if total_stops > 0 else 0

                    line_type = transport_line_type(line["raw_title"])

                    # S'afegeix totes les dades estructurades de la línia al registre
                    all_lines_info.append({
                        "line_type": line_type,
                        "clean_title": line["clean_title"],
                        "total_stops": total_stops,
                        "first_stop": first_stop,
                        "last_stop": last_stop,
                        "all_stops_str": all_stops_str,
                        "zones": zones_str,
                        "accessible_stops": accessible_stops,
                        "accessible_pct": accessible_pct,
                        "correspondence_stops": correspondence_stops,
                        "parking_stops": parking_stops,
                        "url": line["url"],
                        "raw_title": line["raw_title"]
                    })

                except Exception as e:
                    print(f"No es van poder extreure les parades: {e}")

        except Exception as e:
            print(f"No s'ha pogut processar la secció {item['type']}: {e}")


    # Extracció d'incidències separades per categoria de transport

    # Definició d'un mapa amb les categories de transport i les seves respectives URLs d'incidències
    categories_map = [
        {"transport_type": "Metro", "url": "https://crtm.es/comunicacion/actualidad-del-servicio/avisos/avisos-metro/"},
        {"transport_type": "Metro Ligero", "url": "https://crtm.es/comunicacion/actualidad-del-servicio/avisos/avisos-metro-ligero/"},
        {"transport_type": "Cercanías", "url": "https://crtm.es/comunicacion/actualidad-del-servicio/avisos/avisos-cercanias/"}
    ]

    for cat in categories_map:
        print(f"\n▶ Llegint avisos de {cat['transport_type']}")
        try:
            # Navegació cap a la pàgina d'avisos de la categoria actual
            if not carregar_pagina(cat["url"]):
                continue

            # Extracció de la data i hora exacta d'actualització de la capçalera de la pàgina
            updated_date = "N/A"
            try:
                date_elem = browser.find_element(By.CSS_SELECTOR, "span[style*='vertical-align: middle']")
                updated_date = date_elem.get_attribute("textContent").strip()
            except:
                pass

            # Localització de tots els blocs individuals d'avisos dins d'aquesta pàgina
            notice_blocks = browser.find_elements(By.CSS_SELECTOR, "div.contAvisosInfo > div")

            for block in notice_blocks:
                try:
                    # Extracció del títol de l'avís
                    h3_elem = block.find_element(By.TAG_NAME, "h3")
                    notice_title = h3_elem.get_attribute("textContent").strip()
                except:
                    continue

                notice_desc = "N/A"
                try:
                    # Extracció de la descripció recorrent els paràgrafs del bloc
                    paragraphs = block.find_elements(By.TAG_NAME, "p")
                    accumulated_text = []
                    for p in paragraphs:
                        t = p.get_attribute("textContent").strip().strip('"\'')
                        if t and not t.startswith("Avisos") and t != "Más información":
                            accumulated_text.append(t)

                    if accumulated_text:
                        notice_desc = " ".join(accumulated_text)
                except:
                    pass

                # Neteges addicionals per eliminar restes de codi JavaScript o botons de retorn
                if "$(" in notice_desc:
                    notice_desc = notice_desc.split("$(")[0].strip()

                texts_to_delete = ["Vover a Avisos", "Volver a Avisos", "Volver", "Tornar", "Más información"]
                for txt in texts_to_delete:
                    if txt in notice_desc:
                        notice_desc = notice_desc.split(txt)[0].strip()

                notice_desc = " ".join(notice_desc.split())

                # Es desa l'avís a la categoria corresponent
                notices_by_category[cat["transport_type"]].append({
                    "title": notice_title,
                    "description": notice_desc,
                    "date": updated_date
                })

            print(f"  {len(notices_by_category[cat['transport_type']])} avisos trobats")

        except Exception as e:
            print(f"Error processant la categoria {cat['url']}: {e}")

finally:
    # Es tanca el navegador tant si l'extracció ha anat bé com si hi ha hagut algun error
    browser.quit()


# Encreuament de dades i generació de CSV
final_csv_rows = []

for line in all_lines_info:
    line_type = line["line_type"]
    line_name = line["clean_title"].lower()

    # Obtenció dels avisos de la seva mateixa tipologia de transport
    category_notices = notices_by_category.get(line_type, [])
    # Busquem que el nom de la línia vagi flanquejat per límits o no sigui seguit d'un altre dígit dintre del títol o descripció de l'avís.
    matching_notices = []
    for notice in category_notices:
        notice_text = (notice["title"] + " " + notice["description"]).lower()
        pattern = r'\b' + re.escape(line_name) + r'(?!\d)\b'

        if re.search(pattern, notice_text):
            matching_notices.append(notice)

    # Generació de les línies del CSV
    # Si hi ha incidències les incloguem a la línia, si no, posem N/A
    notices_to_process = matching_notices if matching_notices else [{"title": "N/A", "description": "N/A", "date": "N/A"}]

    for notice in notices_to_process:
        has_incident = "Sí" if matching_notices else "No"

        final_csv_rows.append({
            "Tipus_Transport": line["line_type"],
            "Nom_Línia": line["clean_title"],
            "Nombre_Parades": line["total_stops"],
            "Parada_Inici": line["first_stop"],
            "Parada_Final": line["last_stop"],
            "Totes_Les_Parades": line["all_stops_str"],
            "Zones_Tarifàries": line["zones"],
            "Estacions_Accessibles": line["accessible_stops"],
            "Percentatge_Accessibles": line["accessible_pct"],
            "Estacions_Correspondència": line["correspondence_stops"],
            "Estacions_Aparcament": line["parking_stops"],
            "Té_Incidència": has_incident,
            "Títol_Incidència": notice["title"],
            "Descripcio_Incidència": notice["description"],
            "Data_Actualització_Incidència": notice["date"],
            "Data_Captura": capture_date
        })

# Descarregar les dades en un fitxer CSV
if final_csv_rows:
    script_path = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(script_path, "..", "dataset")
    os.makedirs(dataset_path, exist_ok=True)
    filename = os.path.join(dataset_path, f"CTMData_{current_date}.csv")
    keys = final_csv_rows[0].keys()

    with open(filename, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, delimiter=";")
        writer.writeheader()
        writer.writerows(final_csv_rows)

    print(f"\n Fitxer desat amb èxit a la carpeta dataset: {os.path.normpath(filename)}")
else:
    print("\nNo s'han pogut recopilar dades per desar.")

print("\nOperació finalitzada.")