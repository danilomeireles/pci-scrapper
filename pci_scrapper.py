import json
import os
import time
from playwright.sync_api import sync_playwright, Error as PlaywrightError

DEFAULT_PAGE_LOAD_TIMEOUT = 60000  # Milliseconds (60 seconds)
DEFAULT_NAVIGATION_RETRIES = 2  # Results in (1 initial + 2 retries) = 3 attempts


def navigate_with_retry(page, url, wait_strategy="networkidle", timeout=DEFAULT_PAGE_LOAD_TIMEOUT,
                        retries=DEFAULT_NAVIGATION_RETRIES):
    for attempt in range(retries + 1):
        try:
            current_timeout = timeout + (attempt * 15000)
            page.goto(url, wait_until=wait_strategy, timeout=current_timeout)
            return True
        except PlaywrightError as e:
            print(f"Playwright Error (Attempt {attempt + 1}/{retries + 1}) navigating to {url}: {e}")
            if attempt == retries:
                print(f"All navigation attempts failed for {url}.")
                return False
            time.sleep(3 + attempt * 2)
    return False


def extract_pdf_urls_from_page(page, exam_url):
    print(f"Extracting PDF URLs from {exam_url}")

    if not navigate_with_retry(page, exam_url, wait_strategy="networkidle"):
        return []

    pdf_links = page.evaluate("""() => {
        const pdfLinks = [];
        const allLinks = document.querySelectorAll("a");
        const baseUrl = window.location.origin;

        for (const link of allLinks) {
            if (link.textContent.includes("Baixar")) {
                const href = link.getAttribute("href");
                if (href && href.includes(".pdf")) {
                    pdfLinks.push(href.startsWith("http") ? href : baseUrl + href);
                }
            }
        }

        if (pdfLinks.length === 0) {
            for (const link of allLinks) {
                const href = link.getAttribute("href");
                if (href && href.includes(".pdf")) {
                    pdfLinks.push(href.startsWith("http") ? href : baseUrl + href);
                }
            }
        }
        return [...new Set(pdfLinks)];
    }""")

    return pdf_links


def extract_exam_links_from_cargo_page(page, cargo_url):
    print(f"Extracting exam links from {cargo_url}")

    if not navigate_with_retry(page, cargo_url, wait_strategy="load"):
        return []

    exam_links = page.evaluate("""() => {
        const examLinks = [];
        const rows = document.querySelectorAll("table tr");

        for (let i = 1; i < rows.length; i++) {
            const row = rows[i];
            const firstCell = row.querySelector("td:first-child");
            if (firstCell) {
                const linkElement = firstCell.querySelector("a");
                if (linkElement && linkElement.href) {
                    examLinks.push({
                        url: linkElement.href,
                        position: linkElement.textContent.trim(),
                        year: row.querySelector("td:nth-child(2)")?.textContent.trim() || "",
                        agency: row.querySelector("td:nth-child(3) a")?.textContent.trim() || "",
                        organizer: row.querySelector("td:nth-child(4) a")?.textContent.trim() || "",
                        level: row.querySelector("td:nth-child(5)")?.textContent.trim() || ""
                    });
                }
            }
        }
        return examLinks;
    }""")

    return exam_links


def save_single_exam_to_json(exam_data, file_path):
    """Save a single exam entry to the JSON file immediately"""
    try:
        # Load existing data
        existing_data = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)

        # Add new exam data
        existing_data.append(exam_data)

        # Save updated data
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving exam data to {file_path}: {e}")
        return False


def update_existing_exam_in_json(exam_data, exam_index, file_path):
    """Update an existing exam entry in the JSON file"""
    try:
        # Load existing data
        with open(file_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

        # Update the specific exam
        existing_data[exam_index] = exam_data

        # Save updated data
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error updating exam data in {file_path}: {e}")
        return False


def process_cargo_page(page, cargo_name, cargo_url, all_exams_data_list, output_json_file):
    print(f"Processing cargo: {cargo_name} at {cargo_url}")

    exam_link_list = extract_exam_links_from_cargo_page(page, cargo_url)

    if not exam_link_list:
        print(f"No exam links found or failed to load page for {cargo_name} at {cargo_url}. Skipping.")
        return

    print(f"Found {len(exam_link_list)} exam links for {cargo_name}")

    for i, exam_details in enumerate(exam_link_list):
        exam_details['cargo_source'] = cargo_name

        position = exam_details.get('position', 'N/A')
        agency = exam_details.get('agency', 'N/A')
        year = exam_details.get('year', 'N/A')

        print(f"Processing exam {i + 1}/{len(exam_link_list)}: {position} - {agency} - {year}")

        current_exam_key = f"{position} - {agency} - {year}"

        found_exam_index = -1
        for idx, existing_exam in enumerate(all_exams_data_list):
            existing_key = f"{existing_exam.get('position', '')} - {existing_exam.get('agency', '')} - {existing_exam.get('year', '')}"
            if existing_key == current_exam_key:
                found_exam_index = idx
                break

        if found_exam_index != -1 and 'PdfUrls' in all_exams_data_list[found_exam_index]:
            print(f"Data for '{current_exam_key}' with PDF URLs already processed. Updating other details.")
            all_exams_data_list[found_exam_index].update(exam_details)
            update_existing_exam_in_json(all_exams_data_list[found_exam_index], found_exam_index, output_json_file)
            time.sleep(0.5)
            continue

        pdf_urls = extract_pdf_urls_from_page(page, exam_details["url"])

        if found_exam_index != -1:
            # Update existing exam
            all_exams_data_list[found_exam_index].update(exam_details)
            all_exams_data_list[found_exam_index]['PdfUrls'] = pdf_urls if pdf_urls else []
            update_existing_exam_in_json(all_exams_data_list[found_exam_index], found_exam_index, output_json_file)
            if pdf_urls:
                print(f"Updated PDF URLs for existing entry '{current_exam_key}'")
            else:
                print(f"No new PDF URLs found or page load failed for '{current_exam_key}'.")
        else:
            # Add new exam
            new_exam_entry = exam_details.copy()
            new_exam_entry['PdfUrls'] = pdf_urls if pdf_urls else []
            all_exams_data_list.append(new_exam_entry)
            save_single_exam_to_json(new_exam_entry, output_json_file)
            if pdf_urls:
                print(f"Added new exam for '{current_exam_key}' with PDF URLs.")
            else:
                print(f"Added new exam for '{current_exam_key}' (no PDF URLs found or page load failed).")

            print(f"Total exams added: {len(all_exams_data_list)}\n")

        time.sleep(2)

    print(f"Completed processing {cargo_name}")


def load_existing_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                print(f"Warning: Content of {file_path} was not a list. Reinitializing.")
                return []
            print(f"Successfully loaded {len(data)} existing entries from {file_path}.")
            return data
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {file_path}. File will be reinitialized.")
        except Exception as e:
            print(f"An unexpected error occurred while loading {file_path}: {e}. File will be reinitialized.")
    else:
        print(f"{file_path} not found. A new file will be created.")
    return []


def create_initial_json_file(file_path):
    """Create an empty JSON file if it doesn't exist"""
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"Created initial empty JSON file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating initial JSON file {file_path}: {e}")
            return False
    else:
        print(f"JSON file {file_path} already exists.")
        return True


def save_data_to_json(data, file_path):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")
        return False


def main():
    output_json_file = "output.json"

    # Create the JSON file immediately if it doesn't exist
    if not create_initial_json_file(output_json_file):
        print("The output.json file already exists and will be used to add pending exams.")
        return

    # Load existing data
    all_exams_data = load_existing_data(output_json_file)

    base_url = "https://www.pciconcursos.com.br/provas/"
    cargos = [
        "administracao",
        "administrador",
        "administrador-hospitalar",
        "administrador-junior",
        "advogado",
        "advogado-junior",
        "agente-administrativo",
        "agente-administrativo-i",
        "agente-comunitario-de-saude",
        "agente-de-combate-as-endemias",
        "agente-de-defesa-civil",
        "agente-de-endemias",
        "agente-de-fiscalizacao",
        "agente-de-policia",
        "agente-de-portaria",
        "agente-de-saude",
        "agente-de-servicos-gerais",
        "agente-de-transito",
        "agente-de-vigilancia-sanitaria",
        "agente-fiscal",
        "agente-municipal-de-transito",
        "agente-operacional",
        "agente-penitenciario",
        "agente-social",
        "almoxarife",
        "analista-administrativo",
        "analista-ambiental",
        "analista-contabil",
        "analista-de-controle-interno",
        "analista-de-informatica",
        "analista-de-recursos-humanos",
        "analista-de-sistema",
        "analista-de-sistemas",
        "analista-de-suporte",
        "analista-de-tecnologia-da-informacao",
        "analista-financeiro",
        "analista-judiciario-administrativa",
        "analista-judiciario-analise-de-sistemas",
        "analista-judiciario-arquitetura",
        "analista-judiciario-arquivologia",
        "analista-judiciario-assistente-social",
        "analista-judiciario-biblioteconomia",
        "analista-judiciario-contabilidade",
        "analista-judiciario-engenharia-civil",
        "analista-judiciario-engenharia-eletrica",
        "analista-judiciario-estatistica",
        "analista-judiciario-execucao-de-mandados",
        "analista-judiciario-medicina",
        "analista-judiciario-odontologia",
        "analista-judiciario-psicologia",
        "analista-juridico",
        "arquiteto",
        "arquiteto-e-urbanista",
        "arquivista",
        "arquivologista",
        "assessor-juridico",
        "assistente-administrativo",
        "assistente-administrativo-i",
        "assistente-de-administracao",
        "assistente-de-alunos",
        "assistente-de-informatica",
        "assistente-de-laboratorio",
        "assistente-em-administracao",
        "assistente-juridico",
        "assistente-legislativo",
        "assistente-social",
        "assistente-tecnico",
        "assistente-tecnico-administrativo",
        "atendente",
        "atendente-de-consultorio-dentario",
        "atendente-de-farmacia",
        "auditor",
        "auditor-fiscal",
        "auxiliar-administrativo",
        "auxiliar-de-administracao",
        "auxiliar-de-almoxarifado",
        "auxiliar-de-biblioteca",
        "auxiliar-de-consultorio-dentario",
        "auxiliar-de-consultorio-odontologico",
        "auxiliar-de-contabilidade",
        "auxiliar-de-cozinha",
        "auxiliar-de-creche",
        "auxiliar-de-dentista",
        "auxiliar-de-enfermagem",
        "auxiliar-de-enfermagem-do-trabalho",
        "auxiliar-de-farmacia",
        "auxiliar-de-laboratorio",
        "auxiliar-de-manutencao",
        "auxiliar-de-mecanico",
        "auxiliar-de-odontologia",
        "auxiliar-de-saude-bucal",
        "auxiliar-de-secretaria",
        "auxiliar-de-secretaria-escolar",
        "auxiliar-de-servicos",
        "auxiliar-de-servicos-gerais",
        "auxiliar-em-administracao",
        "auxiliar-em-enfermagem",
        "auxiliar-em-saude-bucal",
        "auxiliar-odontologico",
        "auxiliar-operacional",
        "bibliotecario",
        "bibliotecario-documentalista",
        "biblioteconomista",
        "biologo",
        "biomedico",
        "bioquimico",
        "bombeiro",
        "bombeiro-hidraulico",
        "borracheiro",
        "calceteiro",
        "cargos-ensino-fundamental",
        "cargos-ensino-fundamental-completo",
        "cargos-ensino-fundamental-incompleto",
        "cargos-ensino-medio",
        "carpinteiro",
        "ciencias-contabeis",
        "cirurgiao-dentista",
        "contador",
        "contador-junior",
        "continuo",
        "controlador-interno",
        "coordenador-pedagogico",
        "coveiro",
        "cozinheira",
        "cozinheiro",
        "defensor-publico",
        "delegado-de-policia",
        "dentista",
        "desenhista",
        "desenhista-projetista",
        "digitador",
        "direito",
        "economista",
        "economista-junior",
        "educacao-fisica",
        "educador-fisico",
        "educador-infantil",
        "educador-social",
        "eletricista",
        "encanador",
        "enfermagem",
        "enfermeiro",
        "enfermeiro-psf",
        "enfermeiro-do-trabalho",
        "enfermeiro-padrao",
        "enfermeiro-plantonista",
        "engenharia-civil",
        "engenharia-eletrica",
        "engenharia-mecanica",
        "engenheiro",
        "engenheiro-agrimensor",
        "engenheiro-agronomo",
        "engenheiro-ambiental",
        "engenheiro-cartografico",
        "engenheiro-civil",
        "engenheiro-civil-junior",
        "engenheiro-de-alimentos",
        "engenheiro-de-pesca",
        "engenheiro-de-producao",
        "engenheiro-de-seguranca-do-trabalho",
        "engenheiro-de-telecomunicacoes",
        "engenheiro-eletricista",
        "engenheiro-eletrico",
        "engenheiro-eletronico",
        "engenheiro-florestal",
        "engenheiro-mecanico",
        "engenheiro-quimico",
        "engenheiro-sanitarista",
        "escriturario",
        "especialista-em-educacao",
        "estagio-em-direito",
        "estatistico",
        "farmaceutico",
        "fiscal",
        "fiscal-ambiental",
        "fiscal-de-meio-ambiente",
        "fiscal-de-obras",
        "fiscal-de-obras-e-posturas",
        "fiscal-de-posturas",
        "fiscal-de-tributos",
        "fiscal-de-vigilancia-sanitaria",
        "fiscal-municipal",
        "fiscal-sanitario",
        "fiscal-tributario",
        "fisico",
        "fisioterapeuta",
        "fisioterapia",
        "fotografo",
        "gari",
        "geografo",
        "geologo",
        "guarda-municipal",
        "historiador",
        "inspetor-de-alunos",
        "instrutor-de-informatica",
        "instrutor-de-libras",
        "interprete-de-libras",
        "jardineiro",
        "jornalista",
        "juiz",
        "juiz-do-trabalho",
        "juiz-do-trabalho-substituto",
        "juiz-federal-substituto",
        "juiz-substituto",
        "marceneiro",
        "mecanico",
        "medico",
        "medico-cardiologia",
        "medico-cirurgia-geral",
        "medico-cirurgia-pediatrica",
        "medico-clinica-medica",
        "medico-dermatologia",
        "medico-endocrinologia",
        "medico-medicina-do-trabalho",
        "medico-neurocirurgia",
        "medico-neurologia",
        "medico-oftalmologia",
        "medico-otorrinolaringologia",
        "medico-pediatria",
        "medico-pneumologia",
        "medico-psf",
        "medico-psiquiatria",
        "medico-urologia",
        "medico-anestesiologista",
        "medico-cardiologista",
        "medico-cirurgiao-geral",
        "medico-clinico-geral",
        "medico-da-familia",
        "medico-ginecologista",
        "medico-ginecologista-e-obstetra",
        "medico-hematologista",
        "medico-infectologista",
        "medico-intensivista",
        "medico-nefrologista",
        "medico-neurologista",
        "medico-obstetra",
        "medico-oftalmologista",
        "medico-ortopedista",
        "medico-pediatra",
        "medico-plantonista",
        "medico-psiquiatra",
        "medico-radiologista",
        "medico-veterinario",
        "merendeira",
        "mestre-de-obras",
        "monitor",
        "monitor-de-creche",
        "monitor-de-informatica",
        "motorista",
        "motorista-d",
        "motorista-de-ambulancia",
        "motorista-de-veiculos-leves",
        "motorista-de-veiculos-pesados",
        "musico",
        "nutricionista",
        "odontologo",
        "odontologo-endodontia",
        "odontologo-psf",
        "oficial",
        "oficial-administrativo",
        "oficial-de-justica",
        "operador-de-computador",
        "operador-de-maquina",
        "operador-de-maquinas-agricolas",
        "operador-de-maquinas-pesadas",
        "operario",
        "orientador-educacional",
        "orientador-pedagogico",
        "orientador-social",
        "pedagogo",
        "pedreiro",
        "perito-criminal",
        "pintor",
        "porteiro",
        "procurador",
        "procurador-juridico",
        "professor",
        "professor-artes",
        "professor-biologia",
        "professor-ciencias",
        "professor-educacao-fisica",
        "professor-educacao-infantil",
        "professor-ensino-religioso",
        "professor-espanhol",
        "professor-fisica",
        "professor-geografia",
        "professor-historia",
        "professor-informatica",
        "professor-ingles",
        "professor-lingua-inglesa",
        "professor-lingua-portuguesa",
        "professor-matematica",
        "professor-portugues",
        "professor-quimica",
        "professor-series-iniciais",
        "professor-de-1-a-4-series",
        "professor-de-arte",
        "professor-de-artes",
        "professor-de-biologia",
        "professor-de-ciencias",
        "professor-de-educacao-artistica",
        "professor-de-educacao-basica",
        "professor-de-educacao-basica-i",
        "professor-de-educacao-basica-ii-matematica",
        "professor-de-educacao-especial",
        "professor-de-educacao-fisica",
        "professor-de-educacao-infantil",
        "professor-de-ensino-fundamental",
        "professor-de-ensino-religioso",
        "professor-de-espanhol",
        "professor-de-filosofia",
        "professor-de-fisica",
        "professor-de-geografia",
        "professor-de-historia",
        "professor-de-informatica",
        "professor-de-ingles",
        "professor-de-libras",
        "professor-de-matematica",
        "professor-de-musica",
        "professor-de-portugues",
        "professor-de-quimica",
        "professor-de-sociologia",
        "programador",
        "programador-de-computador",
        "programador-visual",
        "psicologo",
        "psicologo-clinico",
        "psicopedagogo",
        "publicitario",
        "recepcionista",
        "relacoes-publicas",
        "sanitarista",
        "secretaria",
        "secretario-de-escola",
        "secretario-escolar",
        "secretario-executivo",
        "serralheiro",
        "servente",
        "servente-de-pedreiro",
        "servicos-gerais",
        "sociologo",
        "soldador",
        "supervisor-de-ensino",
        "tecnico-administrativo",
        "tecnico-agricola",
        "tecnico-de-enfermagem",
        "tecnico-de-informatica",
        "tecnico-de-laboratorio",
        "tecnico-de-seguranca-do-trabalho",
        "tecnico-em-radiologia",
        "tecnico-em-saude-bucal",
        "telefonista",
        "terapeuta-ocupacional",
        "tesoureiro",
        "topografo",
        "tratorista",
        "veterinario",
        "vigia",
        "vigilante",
        "zelador"
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        page = context.new_page()

        for i, path in enumerate(cargos):
            cargo_url = base_url + path
            cargo_name = path.replace('-', ' ').title()
            print(f"\nProcessing CARGO {i + 1}/{len(cargos)}: {cargo_name}")
            process_cargo_page(page, cargo_name, cargo_url, all_exams_data, output_json_file)

            time.sleep(3)

        browser.close()

    print(f"\nAll data successfully saved to {output_json_file}")
    print("PDF URL extraction completed!")


if __name__ == "__main__":
    main()