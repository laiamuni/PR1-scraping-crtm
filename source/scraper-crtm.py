# Instal·lació de les llibreries necessàries
from selenium import webdriver
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import time
import os
import csv
import re

current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Funció per verificar el fitxer robots.txt
def get_robot_txt(url):
    if url.endswith('/'):
        path = url
    else:
        path = url + '/'

    try:
        request = requests.get(path + "robots.txt", data=None)
        return request.text
    except Exception as e:
        return f"No s'ha pogut llegir robots.txt: {e}"

# Lloc web objectiu
URL = "https://crtm.es/"
print(get_robot_txt(URL))

# Configuració bàsica
option = Options()
#option.add_argument("--headless=new")                     
option.add_argument("--incognito")                     
option.add_argument("user-agent=AcademicUOC")     

# Inicialitzar navegador
browser = webdriver.Chrome(options=option)

# Estructura per guardar la informació de les línies per categoria de transport
all_lines_info = []

transport_line_type = lambda title: (
    "Cercanías" if "cercanías" in title.lower() 
    else "Metro Ligero" if "metro ligero" in title.lower()
    else "Metro"
)


# Extracció de línies i parades de transports
browser.get("https://crtm.es/tu-transporte-publico/")
time.sleep(5)

transport_sections = [
    {"type": "Metro", "selector_titulo": "a[title='Metro']"},
    {"type": "Metro Ligero / Tranvía", "selector_titulo": "a[title='Metro Ligero / Tranvía']"},
    {"type": "Cercanías", "selector_titulo": "a[title*='Cercanías']"}
]

for item in transport_sections:
    try:
        # Localització de l'element principal del transport actual i el seu bloc contenidor
        main_link = browser.find_element(By.CSS_SELECTOR, f"div.modMosaico h3.titu8 {item['selector_titulo']}")
        block = main_link.find_element(By.XPATH, "./ancestor::div[@class='modMosaico']")
        # Cerquem l'enllaç específic que de la llista de línies d'aquest transport
        link_lines = block.find_element(By.CSS_SELECTOR, "ul li a[title*='Línea'], ul li a[title*='línea']")
        
        url_lines = link_lines.get_attribute("href")
        
        if url_lines:
            # Navegació cap a la pàgina de línies d'aquesta secció
            browser.get(url_lines)
            time.sleep(3)
            
            extracted_lines = []
            try:
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
                        
                # S'accedeix individualment a l'URL de cada línia per extreure'n les parades
                for line in extracted_lines:
                    browser.get(line["url"])
                    time.sleep(3)
                    
                    stop_names = []
                    try:
                        # Selecció de l'enllaç que va immediatament després de la icona 'ico' dins de la primera cel·la de la fila
                        stop_elements = browser.find_elements(By.CSS_SELECTOR, "table.tablaParadas tr td:first-child span.ico ~ a")
                        for elem in stop_elements:
                            name = elem.get_attribute("textContent").strip()
                            # Filtració de textos de servei o enllaços buits
                            if name and not name.startswith("Enlace a la información"):
                                stop_names.append(name)

                        # Càlculs bàsics dels paràmetres
                        total_stops = len(stop_names)
                        first_stop = stop_names[0] if total_stops > 0 else "N/A"
                        last_stop = stop_names[-1] if total_stops > 0 else "N/A"
                        all_stops_str = ", ".join(stop_names) if total_stops > 0 else "N/A"
                        
                        line_type = transport_line_type(line["raw_title"])

                        # S'afegeix totes les dades estructurades de la línia al registre
                        all_lines_info.append({
                            "line_type": line_type,
                            "clean_title": line["clean_title"],
                            "total_stops": total_stops,
                            "first_stop": first_stop,
                            "last_stop": last_stop,
                            "all_stops_str": all_stops_str,
                            "url": line["url"],
                            "raw_title": line["raw_title"]
                        })
                        
                    except Exception as e:
                        print(f"No es van poder extreure les parades: {e}")
                    
                    browser.back()
                    time.sleep(2)

            except Exception as e:
                print(f"Error en extreure les línies: {e}")
            
            browser.back()
            time.sleep(2)

    except Exception as e:
        print(f"No s'ha pogut processar la secció {item['type']}: {e}")


# Extracció d'incidències separades per categoria de transport

# Definició d'un mapa amb les categories de transport i les seves respectives URLs d'incidències
categories_map = [
    {"transport_type": "Metro", "url": "https://crtm.es/comunicacion/actualidad-del-servicio/avisos/avisos-metro/"},
    {"transport_type": "Metro Ligero", "url": "https://crtm.es/comunicacion/actualidad-del-servicio/avisos/avisos-metro-ligero/"},
    {"transport_type": "Cercanías", "url": "https://crtm.es/comunicacion/actualidad-del-servicio/avisos/avisos-cercanias/"}
]

# Diccionari per emmagatzemar i classificar les incidències recollides segons el seu tipus de transport
notices_by_category = {"Metro": [], "Metro Ligero": [], "Cercanías": []}

for cat in categories_map:
    try:
        # Navegació cap a la pàgina d'avisos de la categoria actual
        browser.get(cat["url"])
        time.sleep(3)
        
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

    except Exception as e:
        print(f"Error processant la categoria {cat['url']}: {e}")

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
            "Té_Incidència": has_incident,
            "Títol_Incidència": notice["title"],
            "Descripcio_Incidència": notice["description"],
            "Data_Actualització_Incidència": notice["date"]
        })

# Descarregar les dades en un fitxer CSV
if final_csv_rows:
    #download_path = os.path.expanduser("~\\Downloads")
    #filename = os.path.join(download_path, f"CTMData_{current_date}_Powered_by_CRTM.csv")
    script_path = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(script_path, "..", "dataset")
    os.makedirs(dataset_path, exist_ok=True)
    filename = os.path.join(dataset_path, f"CTMData_{current_date}.csv")
    keys = final_csv_rows[0].keys()
    
    with open(filename, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, delimiter=";")
        writer.writeheader()
        writer.writerows(final_csv_rows)
        
    print(f"\n Fitxer desat amb èxit a la carpeta de Descàrregues: {filename}")
else:
    print("\nNo s'han pogut recopilar dades per desar.")

browser.quit()
print("\nOperació finalitzada.")
