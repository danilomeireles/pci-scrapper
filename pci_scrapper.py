import json
import os
import time
from playwright.sync_api import sync_playwright, Error as PlaywrightError

DEFAULT_PAGE_LOAD_TIMEOUT = 60000  # Milliseconds (60 seconds)
DEFAULT_NAVIGATION_RETRIES = 2  # Results in (1 initial + 2 retries) = 3 attempts


def navigate_with_retry(page, url, wait_strategy="networkidle", timeout=DEFAULT_PAGE_LOAD_TIMEOUT,
                        retries=DEFAULT_NAVIGATION_RETRIES):
    """Attempts to navigate to a URL with a retry mechanism."""
    for attempt in range(retries + 1):
        try:
            # Increase timeout for subsequent retries
            current_timeout = timeout + (attempt * 15000)
            page.goto(url, wait_until=wait_strategy, timeout=current_timeout)
            return True
        except PlaywrightError as e:
            print(f"Playwright Error (Attempt {attempt + 1}/{retries + 1}) navigating to {url}: {e}")
            if attempt == retries:
                print(f"All navigation attempts failed for {url}.")
                return False
            time.sleep(3 + attempt * 2)  # Basic backoff
    return False


def extract_pdf_urls_from_page(page, exam_url):
    """Extracts PDF URLs from a given exam detail page URL."""
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
    """Extracts exam links from a given cargo (job role) page URL."""
    print(f"Extracting exam links from {cargo_url}")

    # Cargo list pages are often simpler; "load" might be faster and sufficient.
    if not navigate_with_retry(page, cargo_url, wait_strategy="load"):
        return []

    exam_links = page.evaluate("""() => {
        const examLinks = [];
        const rows = document.querySelectorAll("table tr");

        for (let i = 1; i < rows.length; i++) { // Skip header row
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


def process_cargo_page(page, cargo_name, cargo_url, all_exams_data_list):
    """Processes a single cargo page: extracts its exams and their PDF URLs."""
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

        # If exam exists and already has PdfUrls (even an empty list), update details and skip PDF fetching
        if found_exam_index != -1 and 'PdfUrls' in all_exams_data_list[found_exam_index]:
            print(f"Data for '{current_exam_key}' with PDF URLs already processed. Updating other details.")
            all_exams_data_list[found_exam_index].update(exam_details)
            time.sleep(0.5)
            continue

        pdf_urls = extract_pdf_urls_from_page(page, exam_details["url"])

        if found_exam_index != -1:
            # Exam exists but PdfUrls were not fetched previously or were missing
            all_exams_data_list[found_exam_index].update(exam_details)
            all_exams_data_list[found_exam_index]['PdfUrls'] = pdf_urls if pdf_urls else []
            if pdf_urls:
                print(f"Updated PDF URLs for existing entry '{current_exam_key}'")
            else:
                print(f"No new PDF URLs found or page load failed for '{current_exam_key}'.")
        else:
            new_exam_entry = exam_details.copy()
            new_exam_entry['PdfUrls'] = pdf_urls if pdf_urls else []
            all_exams_data_list.append(new_exam_entry)
            if pdf_urls:
                print(f"Added new entry for '{current_exam_key}' with PDF URLs.")
            else:
                print(f"Added new entry for '{current_exam_key}' (no PDF URLs found or page load failed).")

        time.sleep(2)

    print(f"Completed processing {cargo_name}")


def load_existing_data(file_path):
    """Loads existing data from a JSON file."""
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


def save_data_to_json(data, file_path):
    """Saves data to a JSON file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")
        return False


def main():
    output_json_file = "output.json"
    all_exams_data = load_existing_data(output_json_file)

    cargos = [
        {"name": "Administração", "url": "https://www.pciconcursos.com.br/provas/administracao"},
        {"name": "Administrador", "url": "https://www.pciconcursos.com.br/provas/administrador"},
        {"name": "Administrador Hospitalar", "url": "https://www.pciconcursos.com.br/provas/administrador-hospitalar"},
        {"name": "Administrador Júnior", "url": "https://www.pciconcursos.com.br/provas/administrador-junior"},
        {"name": "Advogado", "url": "https://www.pciconcursos.com.br/provas/advogado"},
        {"name": "Advogado Júnior", "url": "https://www.pciconcursos.com.br/provas/advogado-junior"},
        {"name": "Agente Administrativo", "url": "https://www.pciconcursos.com.br/provas/agente-administrativo"},
        {"name": "Agente Administrativo I", "url": "https://www.pciconcursos.com.br/provas/agente-administrativo-i"},
        {"name": "Agente Comunitário de Saúde",
         "url": "https://www.pciconcursos.com.br/provas/agente-comunitario-de-saude"},
        {"name": "Agente de Combate as Endemias",
         "url": "https://www.pciconcursos.com.br/provas/agente-de-combate-as-endemias"},
        {"name": "Agente de Defesa Civil", "url": "https://www.pciconcursos.com.br/provas/agente-de-defesa-civil"},
        {"name": "Agente de Endemias", "url": "https://www.pciconcursos.com.br/provas/agente-de-endemias"},
        {"name": "Agente de Fiscalização", "url": "https://www.pciconcursos.com.br/provas/agente-de-fiscalizacao"},
        {"name": "Agente de Polícia", "url": "https://www.pciconcursos.com.br/provas/agente-de-policia"},
        {"name": "Agente de Portaria", "url": "https://www.pciconcursos.com.br/provas/agente-de-portaria"},
        {"name": "Agente de Saúde", "url": "https://www.pciconcursos.com.br/provas/agente-de-saude"},
        {"name": "Agente de Serviços Gerais",
         "url": "https://www.pciconcursos.com.br/provas/agente-de-servicos-gerais"},
        {"name": "Agente de Trânsito", "url": "https://www.pciconcursos.com.br/provas/agente-de-transito"},
        {"name": "Agente de Vigilância Sanitária",
         "url": "https://www.pciconcursos.com.br/provas/agente-de-vigilancia-sanitaria"},
        {"name": "Agente Fiscal", "url": "https://www.pciconcursos.com.br/provas/agente-fiscal"},
        {"name": "Agente Municipal de Trânsito",
         "url": "https://www.pciconcursos.com.br/provas/agente-municipal-de-transito"},
        {"name": "Agente Operacional", "url": "https://www.pciconcursos.com.br/provas/agente-operacional"},
        {"name": "Agente Penitenciário", "url": "https://www.pciconcursos.com.br/provas/agente-penitenciario"},
        {"name": "Agente Social", "url": "https://www.pciconcursos.com.br/provas/agente-social"},
        {"name": "Almoxarife", "url": "https://www.pciconcursos.com.br/provas/almoxarife"},
        {"name": "Analista Administrativo", "url": "https://www.pciconcursos.com.br/provas/analista-administrativo"},
        {"name": "Analista Ambiental", "url": "https://www.pciconcursos.com.br/provas/analista-ambiental"},
        {"name": "Analista Contábil", "url": "https://www.pciconcursos.com.br/provas/analista-contabil"},
        {"name": "Analista de Controle Interno",
         "url": "https://www.pciconcursos.com.br/provas/analista-de-controle-interno"},
        {"name": "Analista de Informática", "url": "https://www.pciconcursos.com.br/provas/analista-de-informatica"},
        {"name": "Analista de Recursos Humanos",
         "url": "https://www.pciconcursos.com.br/provas/analista-de-recursos-humanos"},
        {"name": "Analista de Sistema", "url": "https://www.pciconcursos.com.br/provas/analista-de-sistema"},
        {"name": "Analista de Sistemas", "url": "https://www.pciconcursos.com.br/provas/analista-de-sistemas"},
        {"name": "Analista de Suporte", "url": "https://www.pciconcursos.com.br/provas/analista-de-suporte"},
        {"name": "Analista de Tecnologia da Informação",
         "url": "https://www.pciconcursos.com.br/provas/analista-de-tecnologia-da-informacao"},
        {"name": "Analista Financeiro", "url": "https://www.pciconcursos.com.br/provas/analista-financeiro"},
        {"name": "Analista Judiciário - Administrativa",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-administrativa"},
        {"name": "Analista Judiciário - Análise de Sistemas",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-analise-de-sistemas"},
        {"name": "Analista Judiciário - Arquitetura",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-arquitetura"},
        {"name": "Analista Judiciário - Arquivologia",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-arquivologia"},
        {"name": "Analista Judiciário - Assistente Social",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-assistente-social"},
        {"name": "Analista Judiciário - Biblioteconomia",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-biblioteconomia"},
        {"name": "Analista Judiciário - Contabilidade",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-contabilidade"},
        {"name": "Analista Judiciário - Engenharia Civil",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-engenharia-civil"},
        {"name": "Analista Judiciário - Engenharia Elétrica",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-engenharia-eletrica"},
        {"name": "Analista Judiciário - Estatística",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-estatistica"},
        {"name": "Analista Judiciário - Execução de Mandados",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-execucao-de-mandados"},
        {"name": "Analista Judiciário - Medicina",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-medicina"},
        {"name": "Analista Judiciário - Odontologia",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-odontologia"},
        {"name": "Analista Judiciário - Psicologia",
         "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-psicologia"},
        {"name": "Analista Jurídico", "url": "https://www.pciconcursos.com.br/provas/analista-juridico"},
        {"name": "Arquiteto", "url": "https://www.pciconcursos.com.br/provas/arquiteto"},
        {"name": "Arquiteto e Urbanista", "url": "https://www.pciconcursos.com.br/provas/arquiteto-e-urbanista"},
        {"name": "Arquivista", "url": "https://www.pciconcursos.com.br/provas/arquivista"},
        {"name": "Arquivologista", "url": "https://www.pciconcursos.com.br/provas/arquivologista"},
        {"name": "Assessor Jurídico", "url": "https://www.pciconcursos.com.br/provas/assessor-juridico"},
        {"name": "Assistente Administrativo",
         "url": "https://www.pciconcursos.com.br/provas/assistente-administrativo"},
        {"name": "Assistente Administrativo I",
         "url": "https://www.pciconcursos.com.br/provas/assistente-administrativo-i"},
        {"name": "Assistente de Administração",
         "url": "https://www.pciconcursos.com.br/provas/assistente-de-administracao"},
        {"name": "Assistente de Alunos", "url": "https://www.pciconcursos.com.br/provas/assistente-de-alunos"},
        {"name": "Assistente de Informática",
         "url": "https://www.pciconcursos.com.br/provas/assistente-de-informatica"},
        {"name": "Assistente de Laboratório",
         "url": "https://www.pciconcursos.com.br/provas/assistente-de-laboratorio"},
        {"name": "Assistente em Administração",
         "url": "https://www.pciconcursos.com.br/provas/assistente-em-administracao"},
        {"name": "Assistente Jurídico", "url": "https://www.pciconcursos.com.br/provas/assistente-juridico"},
        {"name": "Assistente Legislativo", "url": "https://www.pciconcursos.com.br/provas/assistente-legislativo"},
        {"name": "Assistente Social", "url": "https://www.pciconcursos.com.br/provas/assistente-social"},
        {"name": "Assistente Técnico", "url": "https://www.pciconcursos.com.br/provas/assistente-tecnico"},
        {"name": "Assistente Técnico Administrativo",
         "url": "https://www.pciconcursos.com.br/provas/assistente-tecnico-administrativo"},
        {"name": "Atendente", "url": "https://www.pciconcursos.com.br/provas/atendente"},
        {"name": "Atendente de Consultório Dentário",
         "url": "https://www.pciconcursos.com.br/provas/atendente-de-consultorio-dentario"},
        {"name": "Atendente de Farmácia", "url": "https://www.pciconcursos.com.br/provas/atendente-de-farmacia"},
        {"name": "Auditor", "url": "https://www.pciconcursos.com.br/provas/auditor"},
        {"name": "Auditor Fiscal", "url": "https://www.pciconcursos.com.br/provas/auditor-fiscal"},
        {"name": "Auxiliar Administrativo", "url": "https://www.pciconcursos.com.br/provas/auxiliar-administrativo"},
        {"name": "Auxiliar de Administração",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-administracao"},
        {"name": "Auxiliar de Almoxarifado", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-almoxarifado"},
        {"name": "Auxiliar de Biblioteca", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-biblioteca"},
        {"name": "Auxiliar de Consultório Dentário",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-consultorio-dentario"},
        {"name": "Auxiliar de Consultório Odontológico",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-consultorio-odontologico"},
        {"name": "Auxiliar de Contabilidade",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-contabilidade"},
        {"name": "Auxiliar de Cozinha", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-cozinha"},
        {"name": "Auxiliar de Creche", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-creche"},
        {"name": "Auxiliar de Dentista", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-dentista"},
        {"name": "Auxiliar de Enfermagem", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-enfermagem"},
        {"name": "Auxiliar de Enfermagem do Trabalho",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-enfermagem-do-trabalho"},
        {"name": "Auxiliar de Farmácia", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-farmacia"},
        {"name": "Auxiliar de Laboratório", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-laboratorio"},
        {"name": "Auxiliar de Manutenção", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-manutencao"},
        {"name": "Auxiliar de Mecânico", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-mecanico"},
        {"name": "Auxiliar de Odontologia", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-odontologia"},
        {"name": "Auxiliar de Saúde Bucal", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-saude-bucal"},
        {"name": "Auxiliar de Secretária", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-secretaria"},
        {"name": "Auxiliar de Secretária Escolar",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-secretaria-escolar"},
        {"name": "Auxiliar de Serviços", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-servicos"},
        {"name": "Auxiliar de Serviços Gerais",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-servicos-gerais"},
        {"name": "Auxiliar em Administração",
         "url": "https://www.pciconcursos.com.br/provas/auxiliar-em-administracao"},
        {"name": "Auxiliar em Enfermagem", "url": "https://www.pciconcursos.com.br/provas/auxiliar-em-enfermagem"},
        {"name": "Auxiliar em Saúde Bucal", "url": "https://www.pciconcursos.com.br/provas/auxiliar-em-saude-bucal"},
        {"name": "Auxiliar Odontológico", "url": "https://www.pciconcursos.com.br/provas/auxiliar-odontologico"},
        {"name": "Auxiliar Operacional", "url": "https://www.pciconcursos.com.br/provas/auxiliar-operacional"},
        {"name": "Bibliotecário", "url": "https://www.pciconcursos.com.br/provas/bibliotecario"},
        {"name": "Bibliotecário-Documentalista",
         "url": "https://www.pciconcursos.com.br/provas/bibliotecario-documentalista"},
        {"name": "Biblioteconomista", "url": "https://www.pciconcursos.com.br/provas/biblioteconomista"},
        {"name": "Biólogo", "url": "https://www.pciconcursos.com.br/provas/biologo"},
        {"name": "Biomédico", "url": "https://www.pciconcursos.com.br/provas/biomedico"},
        {"name": "Bioquímico", "url": "https://www.pciconcursos.com.br/provas/bioquimico"},
        {"name": "Bombeiro", "url": "https://www.pciconcursos.com.br/provas/bombeiro"},
        {"name": "Bombeiro Hidráulico", "url": "https://www.pciconcursos.com.br/provas/bombeiro-hidraulico"},
        {"name": "Borracheiro", "url": "https://www.pciconcursos.com.br/provas/borracheiro"},
        {"name": "Calceteiro", "url": "https://www.pciconcursos.com.br/provas/calceteiro"},
        {"name": "Cargos Ensino Fundamental",
         "url": "https://www.pciconcursos.com.br/provas/cargos-ensino-fundamental"},
        {"name": "Cargos Ensino Fundamental Completo",
         "url": "https://www.pciconcursos.com.br/provas/cargos-ensino-fundamental-completo"},
        {"name": "Cargos Ensino Fundamental Incompleto",
         "url": "https://www.pciconcursos.com.br/provas/cargos-ensino-fundamental-incompleto"},
        {"name": "Cargos Ensino Médio", "url": "https://www.pciconcursos.com.br/provas/cargos-ensino-medio"},
        {"name": "Carpinteiro", "url": "https://www.pciconcursos.com.br/provas/carpinteiro"},
        {"name": "Ciências Contábeis", "url": "https://www.pciconcursos.com.br/provas/ciencias-contabeis"},
        {"name": "Cirurgião-Dentista", "url": "https://www.pciconcursos.com.br/provas/cirurgiao-dentista"},
        {"name": "Contador", "url": "https://www.pciconcursos.com.br/provas/contador"},
        {"name": "Contador Júnior", "url": "https://www.pciconcursos.com.br/provas/contador-junior"},
        {"name": "Contínuo", "url": "https://www.pciconcursos.com.br/provas/continuo"},
        {"name": "Controlador Interno", "url": "https://www.pciconcursos.com.br/provas/controlador-interno"},
        {"name": "Coordenador Pedagógico", "url": "https://www.pciconcursos.com.br/provas/coordenador-pedagogico"},
        {"name": "Coveiro", "url": "https://www.pciconcursos.com.br/provas/coveiro"},
        {"name": "Cozinheira", "url": "https://www.pciconcursos.com.br/provas/cozinheira"},
        {"name": "Cozinheiro", "url": "https://www.pciconcursos.com.br/provas/cozinheiro"},
        {"name": "Defensor Público", "url": "https://www.pciconcursos.com.br/provas/defensor-publico"},
        {"name": "Delegado de Polícia", "url": "https://www.pciconcursos.com.br/provas/delegado-de-policia"},
        {"name": "Dentista", "url": "https://www.pciconcursos.com.br/provas/dentista"},
        {"name": "Desenhista", "url": "https://www.pciconcursos.com.br/provas/desenhista"},
        {"name": "Desenhista Projetista", "url": "https://www.pciconcursos.com.br/provas/desenhista-projetista"},
        {"name": "Digitador", "url": "https://www.pciconcursos.com.br/provas/digitador"},
        {"name": "Direito", "url": "https://www.pciconcursos.com.br/provas/direito"},
        {"name": "Economista", "url": "https://www.pciconcursos.com.br/provas/economista"},
        {"name": "Economista Júnior", "url": "https://www.pciconcursos.com.br/provas/economista-junior"},
        {"name": "Educação Física", "url": "https://www.pciconcursos.com.br/provas/educacao-fisica"},
        {"name": "Educador Físico", "url": "https://www.pciconcursos.com.br/provas/educador-fisico"},
        {"name": "Educador Infantil", "url": "https://www.pciconcursos.com.br/provas/educador-infantil"},
        {"name": "Educador Social", "url": "https://www.pciconcursos.com.br/provas/educador-social"},
        {"name": "Eletricista", "url": "https://www.pciconcursos.com.br/provas/eletricista"},
        {"name": "Encanador", "url": "https://www.pciconcursos.com.br/provas/encanador"},
        {"name": "Enfermagem", "url": "https://www.pciconcursos.com.br/provas/enfermagem"},
        {"name": "Enfermeiro", "url": "https://www.pciconcursos.com.br/provas/enfermeiro"},
        {"name": "Enfermeiro PSF", "url": "https://www.pciconcursos.com.br/provas/enfermeiro-psf"},
        {"name": "Enfermeiro do Trabalho", "url": "https://www.pciconcursos.com.br/provas/enfermeiro-do-trabalho"},
        {"name": "Enfermeiro Padrão", "url": "https://www.pciconcursos.com.br/provas/enfermeiro-padrao"},
        {"name": "Enfermeiro Plantonista", "url": "https://www.pciconcursos.com.br/provas/enfermeiro-plantonista"},
        {"name": "Engenharia Civil", "url": "https://www.pciconcursos.com.br/provas/engenharia-civil"},
        {"name": "Engenharia Elétrica", "url": "https://www.pciconcursos.com.br/provas/engenharia-eletrica"},
        {"name": "Engenharia Mecânica", "url": "https://www.pciconcursos.com.br/provas/engenharia-mecanica"},
        {"name": "Engenheiro", "url": "https://www.pciconcursos.com.br/provas/engenheiro"},
        {"name": "Engenheiro Agrimensor", "url": "https://www.pciconcursos.com.br/provas/engenheiro-agrimensor"},
        {"name": "Engenheiro Agrônomo", "url": "https://www.pciconcursos.com.br/provas/engenheiro-agronomo"},
        {"name": "Engenheiro Ambiental", "url": "https://www.pciconcursos.com.br/provas/engenheiro-ambiental"},
        {"name": "Engenheiro Cartográfico", "url": "https://www.pciconcursos.com.br/provas/engenheiro-cartografico"},
        {"name": "Engenheiro Civil", "url": "https://www.pciconcursos.com.br/provas/engenheiro-civil"},
        {"name": "Engenheiro Civil Júnior", "url": "https://www.pciconcursos.com.br/provas/engenheiro-civil-junior"},
        {"name": "Engenheiro de alimentos", "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-alimentos"},
        {"name": "Engenheiro de Pesca", "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-pesca"},
        {"name": "Engenheiro de Produção", "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-producao"},
        {"name": "Engenheiro de Segurança do Trabalho",
         "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-seguranca-do-trabalho"},
        {"name": "Engenheiro de Telecomunicações",
         "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-telecomunicacoes"},
        {"name": "Engenheiro Eletricista", "url": "https://www.pciconcursos.com.br/provas/engenheiro-eletricista"},
        {"name": "Engenheiro Elétrico", "url": "https://www.pciconcursos.com.br/provas/engenheiro-eletrico"},
        {"name": "Engenheiro Eletrônico", "url": "https://www.pciconcursos.com.br/provas/engenheiro-eletronico"},
        {"name": "Engenheiro Florestal", "url": "https://www.pciconcursos.com.br/provas/engenheiro-florestal"},
        {"name": "Engenheiro Mecânico", "url": "https://www.pciconcursos.com.br/provas/engenheiro-mecanico"},
        {"name": "Engenheiro Químico", "url": "https://www.pciconcursos.com.br/provas/engenheiro-quimico"},
        {"name": "Engenheiro Sanitarista", "url": "https://www.pciconcursos.com.br/provas/engenheiro-sanitarista"},
        {"name": "Escriturário", "url": "https://www.pciconcursos.com.br/provas/escriturario"},
        {"name": "Especialista em Educação", "url": "https://www.pciconcursos.com.br/provas/especialista-em-educacao"},
        {"name": "Estágio em Direito", "url": "https://www.pciconcursos.com.br/provas/estagio-em-direito"},
        {"name": "Estatístico", "url": "https://www.pciconcursos.com.br/provas/estatistico"},
        {"name": "Farmacêutico", "url": "https://www.pciconcursos.com.br/provas/farmaceutico"},
        {"name": "Fiscal", "url": "https://www.pciconcursos.com.br/provas/fiscal"},
        {"name": "Fiscal Ambiental", "url": "https://www.pciconcursos.com.br/provas/fiscal-ambiental"},
        {"name": "Fiscal de Meio Ambiente", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-meio-ambiente"},
        {"name": "Fiscal de Obras", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-obras"},
        {"name": "Fiscal de Obras e Posturas",
         "url": "https://www.pciconcursos.com.br/provas/fiscal-de-obras-e-posturas"},
        {"name": "Fiscal de Posturas", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-posturas"},
        {"name": "Fiscal de Tributos", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-tributos"},
        {"name": "Fiscal de Vigilância Sanitária",
         "url": "https://www.pciconcursos.com.br/provas/fiscal-de-vigilancia-sanitaria"},
        {"name": "Fiscal Municipal", "url": "https://www.pciconcursos.com.br/provas/fiscal-municipal"},
        {"name": "Fiscal Sanitário", "url": "https://www.pciconcursos.com.br/provas/fiscal-sanitario"},
        {"name": "Fiscal Tributário", "url": "https://www.pciconcursos.com.br/provas/fiscal-tributario"},
        {"name": "Físico", "url": "https://www.pciconcursos.com.br/provas/fisico"},
        {"name": "Fisioterapeuta", "url": "https://www.pciconcursos.com.br/provas/fisioterapeuta"},
        {"name": "Fisioterapia", "url": "https://www.pciconcursos.com.br/provas/fisioterapia"},
        {"name": "Fotógrafo", "url": "https://www.pciconcursos.com.br/provas/fotografo"},
        {"name": "Gari", "url": "https://www.pciconcursos.com.br/provas/gari"},
        {"name": "Geógrafo", "url": "https://www.pciconcursos.com.br/provas/geografo"},
        {"name": "Geológo", "url": "https://www.pciconcursos.com.br/provas/geologo"},
        {"name": "Guarda Municipal", "url": "https://www.pciconcursos.com.br/provas/guarda-municipal"},
        {"name": "Historiador", "url": "https://www.pciconcursos.com.br/provas/historiador"},
        {"name": "Inspetor de Alunos", "url": "https://www.pciconcursos.com.br/provas/inspetor-de-alunos"},
        {"name": "Instrutor de Informática", "url": "https://www.pciconcursos.com.br/provas/instrutor-de-informatica"},
        {"name": "Instrutor de Libras", "url": "https://www.pciconcursos.com.br/provas/instrutor-de-libras"},
        {"name": "Intérprete de Libras", "url": "https://www.pciconcursos.com.br/provas/interprete-de-libras"},
        {"name": "Jardineiro", "url": "https://www.pciconcursos.com.br/provas/jardineiro"},
        {"name": "Jornalista", "url": "https://www.pciconcursos.com.br/provas/jornalista"},
        {"name": "Juiz", "url": "https://www.pciconcursos.com.br/provas/juiz"},
        {"name": "Juiz do Trabalho", "url": "https://www.pciconcursos.com.br/provas/juiz-do-trabalho"},
        {"name": "Juiz do Trabalho Substituto",
         "url": "https://www.pciconcursos.com.br/provas/juiz-do-trabalho-substituto"},
        {"name": "Juiz Federal Substituto", "url": "https://www.pciconcursos.com.br/provas/juiz-federal-substituto"},
        {"name": "Juiz Substituto", "url": "https://www.pciconcursos.com.br/provas/juiz-substituto"},
        {"name": "Marceneiro", "url": "https://www.pciconcursos.com.br/provas/marceneiro"},
        {"name": "Mecânico", "url": "https://www.pciconcursos.com.br/provas/mecanico"},
        {"name": "Médico", "url": "https://www.pciconcursos.com.br/provas/medico"},
        {"name": "Médico - Cardiologia", "url": "https://www.pciconcursos.com.br/provas/medico-cardiologia"},
        {"name": "Médico - Cirurgia Geral", "url": "https://www.pciconcursos.com.br/provas/medico-cirurgia-geral"},
        {"name": "Médico - Cirurgia Pediátrica",
         "url": "https://www.pciconcursos.com.br/provas/medico-cirurgia-pediatrica"},
        {"name": "Médico Clínica Médica", "url": "https://www.pciconcursos.com.br/provas/medico-clinica-medica"},
        {"name": "Médico - Dermatologia", "url": "https://www.pciconcursos.com.br/provas/medico-dermatologia"},
        {"name": "Médico - Endocrinologia", "url": "https://www.pciconcursos.com.br/provas/medico-endocrinologia"},
        {"name": "Médico - Medicina do Trabalho",
         "url": "https://www.pciconcursos.com.br/provas/medico-medicina-do-trabalho"},
        {"name": "Médico - Neurocirurgia", "url": "https://www.pciconcursos.com.br/provas/medico-neurocirurgia"},
        {"name": "Médico - Neurologia", "url": "https://www.pciconcursos.com.br/provas/medico-neurologia"},
        {"name": "Médico - Oftalmologia", "url": "https://www.pciconcursos.com.br/provas/medico-oftalmologia"},
        {"name": "Médico - Otorrinolaringologia",
         "url": "https://www.pciconcursos.com.br/provas/medico-otorrinolaringologia"},
        {"name": "Médico - Pediatria", "url": "https://www.pciconcursos.com.br/provas/medico-pediatria"},
        {"name": "Médico - Pneumologia", "url": "https://www.pciconcursos.com.br/provas/medico-pneumologia"},
        {"name": "Médico PSF", "url": "https://www.pciconcursos.com.br/provas/medico-psf"},
        {"name": "Médico - Psiquiatria", "url": "https://www.pciconcursos.com.br/provas/medico-psiquiatria"},
        {"name": "Médico - Urologia", "url": "https://www.pciconcursos.com.br/provas/medico-urologia"},
        {"name": "Médico Anestesiologista", "url": "https://www.pciconcursos.com.br/provas/medico-anestesiologista"},
        {"name": "Médico Cardiologista", "url": "https://www.pciconcursos.com.br/provas/medico-cardiologista"},
        {"name": "Médico-Cirurgião Geral", "url": "https://www.pciconcursos.com.br/provas/medico-cirurgiao-geral"},
        {"name": "Médico Clínico Geral", "url": "https://www.pciconcursos.com.br/provas/medico-clinico-geral"},
        {"name": "Médico da Família", "url": "https://www.pciconcursos.com.br/provas/medico-da-familia"},
        {"name": "Médico Ginecologista", "url": "https://www.pciconcursos.com.br/provas/medico-ginecologista"},
        {"name": "Médico Ginecologista e Obstetra",
         "url": "https://www.pciconcursos.com.br/provas/medico-ginecologista-e-obstetra"},
        {"name": "Médico Hematologista", "url": "https://www.pciconcursos.com.br/provas/medico-hematologista"},
        {"name": "Médico Infectologista", "url": "https://www.pciconcursos.com.br/provas/medico-infectologista"},
        {"name": "Médico Intensivista", "url": "https://www.pciconcursos.com.br/provas/medico-intensivista"},
        {"name": "Médico Nefrologista", "url": "https://www.pciconcursos.com.br/provas/medico-nefrologista"},
        {"name": "Médico Neurologista", "url": "https://www.pciconcursos.com.br/provas/medico-neurologista"},
        {"name": "Médico Obstetra", "url": "https://www.pciconcursos.com.br/provas/medico-obstetra"},
        {"name": "Médico Oftalmologista", "url": "https://www.pciconcursos.com.br/provas/medico-oftalmologista"},
        {"name": "Médico Ortopedista", "url": "https://www.pciconcursos.com.br/provas/medico-ortopedista"},
        {"name": "Médico Pediatra", "url": "https://www.pciconcursos.com.br/provas/medico-pediatra"},
        {"name": "Médico Plantonista", "url": "https://www.pciconcursos.com.br/provas/medico-plantonista"},
        {"name": "Médico Psiquiatra", "url": "https://www.pciconcursos.com.br/provas/medico-psiquiatra"},
        {"name": "Médico Radiologista", "url": "https://www.pciconcursos.com.br/provas/medico-radiologista"},
        {"name": "Médico Veterinário", "url": "https://www.pciconcursos.com.br/provas/medico-veterinario"},
        {"name": "Merendeira", "url": "https://www.pciconcursos.com.br/provas/merendeira"},
        {"name": "Mestre de Obras", "url": "https://www.pciconcursos.com.br/provas/mestre-de-obras"},
        {"name": "Monitor", "url": "https://www.pciconcursos.com.br/provas/monitor"},
        {"name": "Monitor de Creche", "url": "https://www.pciconcursos.com.br/provas/monitor-de-creche"},
        {"name": "Monitor de Informática", "url": "https://www.pciconcursos.com.br/provas/monitor-de-informatica"},
        {"name": "Motorista", "url": "https://www.pciconcursos.com.br/provas/motorista"},
        {"name": "Motorista \"D\"", "url": "https://www.pciconcursos.com.br/provas/motorista-d"},
        {"name": "Motorista de Ambulância", "url": "https://www.pciconcursos.com.br/provas/motorista-de-ambulancia"},
        {"name": "Motorista de Veículos Leves",
         "url": "https://www.pciconcursos.com.br/provas/motorista-de-veiculos-leves"},
        {"name": "Motorista de Veículos Pesados",
         "url": "https://www.pciconcursos.com.br/provas/motorista-de-veiculos-pesados"},
        {"name": "Músico", "url": "https://www.pciconcursos.com.br/provas/musico"},
        {"name": "Nutricionista", "url": "https://www.pciconcursos.com.br/provas/nutricionista"},
        {"name": "Odontólogo", "url": "https://www.pciconcursos.com.br/provas/odontologo"},
        {"name": "Odontólogo - Endodontia", "url": "https://www.pciconcursos.com.br/provas/odontologo-endodontia"},
        {"name": "Odontólogo - PSF", "url": "https://www.pciconcursos.com.br/provas/odontologo-psf"},
        {"name": "Oficial", "url": "https://www.pciconcursos.com.br/provas/oficial"},
        {"name": "Oficial Administrativo", "url": "https://www.pciconcursos.com.br/provas/oficial-administrativo"},
        {"name": "Oficial de Justiça", "url": "https://www.pciconcursos.com.br/provas/oficial-de-justica"},
        {"name": "Operador de Computador", "url": "https://www.pciconcursos.com.br/provas/operador-de-computador"},
        {"name": "Operador de Máquina", "url": "https://www.pciconcursos.com.br/provas/operador-de-maquina"},
        {"name": "Operador de máquinas agrícolas",
         "url": "https://www.pciconcursos.com.br/provas/operador-de-maquinas-agricolas"},
        {"name": "Operador de Máquinas Pesadas",
         "url": "https://www.pciconcursos.com.br/provas/operador-de-maquinas-pesadas"},
        {"name": "Operário", "url": "https://www.pciconcursos.com.br/provas/operario"},
        {"name": "Orientador Educacional", "url": "https://www.pciconcursos.com.br/provas/orientador-educacional"},
        {"name": "Orientador Pedagógico", "url": "https://www.pciconcursos.com.br/provas/orientador-pedagogico"},
        {"name": "Orientador Social", "url": "https://www.pciconcursos.com.br/provas/orientador-social"},
        {"name": "Pedagogo", "url": "https://www.pciconcursos.com.br/provas/pedagogo"},
        {"name": "Pedreiro", "url": "https://www.pciconcursos.com.br/provas/pedreiro"},
        {"name": "Perito Criminal", "url": "https://www.pciconcursos.com.br/provas/perito-criminal"},
        {"name": "Pintor", "url": "https://www.pciconcursos.com.br/provas/pintor"},
        {"name": "Porteiro", "url": "https://www.pciconcursos.com.br/provas/porteiro"},
        {"name": "Procurador", "url": "https://www.pciconcursos.com.br/provas/procurador"},
        {"name": "Procurador Jurídico", "url": "https://www.pciconcursos.com.br/provas/procurador-juridico"},
        {"name": "Professor", "url": "https://www.pciconcursos.com.br/provas/professor"},
        {"name": "Professor - Artes", "url": "https://www.pciconcursos.com.br/provas/professor-artes"},
        {"name": "Professor - Biologia", "url": "https://www.pciconcursos.com.br/provas/professor-biologia"},
        {"name": "Professor - Ciências", "url": "https://www.pciconcursos.com.br/provas/professor-ciencias"},
        {"name": "Professor - Educação Física",
         "url": "https://www.pciconcursos.com.br/provas/professor-educacao-fisica"},
        {"name": "Professor Educação Infantil",
         "url": "https://www.pciconcursos.com.br/provas/professor-educacao-infantil"},
        {"name": "Professor - Ensino Religioso",
         "url": "https://www.pciconcursos.com.br/provas/professor-ensino-religioso"},
        {"name": "Professor - Espanhol", "url": "https://www.pciconcursos.com.br/provas/professor-espanhol"},
        {"name": "Professor - Física", "url": "https://www.pciconcursos.com.br/provas/professor-fisica"},
        {"name": "Professor - Geografia", "url": "https://www.pciconcursos.com.br/provas/professor-geografia"},
        {"name": "Professor - História", "url": "https://www.pciconcursos.com.br/provas/professor-historia"},
        {"name": "Professor - Informática", "url": "https://www.pciconcursos.com.br/provas/professor-informatica"},
        {"name": "Professor - Inglês", "url": "https://www.pciconcursos.com.br/provas/professor-ingles"},
        {"name": "Professor - Língua Inglesa",
         "url": "https://www.pciconcursos.com.br/provas/professor-lingua-inglesa"},
        {"name": "Professor - Língua Portuguesa",
         "url": "https://www.pciconcursos.com.br/provas/professor-lingua-portuguesa"},
        {"name": "Professor - Matemática", "url": "https://www.pciconcursos.com.br/provas/professor-matematica"},
        {"name": "Professor - Português", "url": "https://www.pciconcursos.com.br/provas/professor-portugues"},
        {"name": "Professor - Química", "url": "https://www.pciconcursos.com.br/provas/professor-quimica"},
        {"name": "Professor - Séries Iniciais",
         "url": "https://www.pciconcursos.com.br/provas/professor-series-iniciais"},
        {"name": "Professor de 1ª a 4ª séries",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-1-a-4-series"},
        {"name": "Professor de Arte", "url": "https://www.pciconcursos.com.br/provas/professor-de-arte"},
        {"name": "Professor de Artes", "url": "https://www.pciconcursos.com.br/provas/professor-de-artes"},
        {"name": "Professor de Biologia", "url": "https://www.pciconcursos.com.br/provas/professor-de-biologia"},
        {"name": "Professor de Ciências", "url": "https://www.pciconcursos.com.br/provas/professor-de-ciencias"},
        {"name": "Professor de Educação Artística",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-artistica"},
        {"name": "Professor de Educação Básica",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-basica"},
        {"name": "Professor de Educação Básica I",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-basica-i"},
        {"name": "Professor de Educação Básica II - Matemática",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-basica-ii-matematica"},
        {"name": "Professor de Educação Especial",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-especial"},
        {"name": "Professor de Educação Física",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-fisica"},
        {"name": "Professor de Educação Infantil",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-infantil"},
        {"name": "Professor de Ensino Fundamental",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-ensino-fundamental"},
        {"name": "Professor de Ensino Religioso",
         "url": "https://www.pciconcursos.com.br/provas/professor-de-ensino-religioso"},
        {"name": "Professor de Espanhol", "url": "https://www.pciconcursos.com.br/provas/professor-de-espanhol"},
        {"name": "Professor de Filosofia", "url": "https://www.pciconcursos.com.br/provas/professor-de-filosofia"},
        {"name": "Professor de Física", "url": "https://www.pciconcursos.com.br/provas/professor-de-fisica"},
        {"name": "Professor de Geografia", "url": "https://www.pciconcursos.com.br/provas/professor-de-geografia"},
        {"name": "Professor de História", "url": "https://www.pciconcursos.com.br/provas/professor-de-historia"},
        {"name": "Professor de Informática", "url": "https://www.pciconcursos.com.br/provas/professor-de-informatica"},
        {"name": "Professor de Inglês", "url": "https://www.pciconcursos.com.br/provas/professor-de-ingles"},
        {"name": "Professor de Libras", "url": "https://www.pciconcursos.com.br/provas/professor-de-libras"},
        {"name": "Professor de Matemática", "url": "https://www.pciconcursos.com.br/provas/professor-de-matematica"},
        {"name": "Professor de Música", "url": "https://www.pciconcursos.com.br/provas/professor-de-musica"},
        {"name": "Professor de Português", "url": "https://www.pciconcursos.com.br/provas/professor-de-portugues"},
        {"name": "Professor de Química", "url": "https://www.pciconcursos.com.br/provas/professor-de-quimica"},
        {"name": "Professor de Sociologia", "url": "https://www.pciconcursos.com.br/provas/professor-de-sociologia"},
        {"name": "Programador", "url": "https://www.pciconcursos.com.br/provas/programador"},
        {"name": "Programador de Computador",
         "url": "https://www.pciconcursos.com.br/provas/programador-de-computador"},
        {"name": "Programador Visual", "url": "https://www.pciconcursos.com.br/provas/programador-visual"},
        {"name": "Psicólogo", "url": "https://www.pciconcursos.com.br/provas/psicologo"},
        {"name": "Psicólogo Clínico", "url": "https://www.pciconcursos.com.br/provas/psicologo-clinico"},
        {"name": "Psicopedagogo", "url": "https://www.pciconcursos.com.br/provas/psicopedagogo"},
        {"name": "Públicitário", "url": "https://www.pciconcursos.com.br/provas/publicitario"},
        {"name": "Recepcionista", "url": "https://www.pciconcursos.com.br/provas/recepcionista"},
        {"name": "Relações Públicas", "url": "https://www.pciconcursos.com.br/provas/relacoes-publicas"},
        {"name": "Sanitarista", "url": "https://www.pciconcursos.com.br/provas/sanitarista"},
        {"name": "Secretária", "url": "https://www.pciconcursos.com.br/provas/secretaria"},
        {"name": "Secretário de Escola", "url": "https://www.pciconcursos.com.br/provas/secretario-de-escola"},
        {"name": "Secretário Escolar", "url": "https://www.pciconcursos.com.br/provas/secretario-escolar"},
        {"name": "Secretário Executivo", "url": "https://www.pciconcursos.com.br/provas/secretario-executivo"},
        {"name": "Serralheiro", "url": "https://www.pciconcursos.com.br/provas/serralheiro"},
        {"name": "Servente", "url": "https://www.pciconcursos.com.br/provas/servente"},
        {"name": "Servente de Pedreiro", "url": "https://www.pciconcursos.com.br/provas/servente-de-pedreiro"},
        {"name": "Serviços Gerais", "url": "https://www.pciconcursos.com.br/provas/servicos-gerais"},
        {"name": "Sociólogo", "url": "https://www.pciconcursos.com.br/provas/sociologo"},
        {"name": "Soldador", "url": "https://www.pciconcursos.com.br/provas/soldador"},
        {"name": "Supervisor de Ensino", "url": "https://www.pciconcursos.com.br/provas/supervisor-de-ensino"},
        {"name": "Técnico Administrativo", "url": "https://www.pciconcursos.com.br/provas/tecnico-administrativo"},
        {"name": "Técnico Agrícola", "url": "https://www.pciconcursos.com.br/provas/tecnico-agricola"},
        {"name": "Técnico de Enfermagem", "url": "https://www.pciconcursos.com.br/provas/tecnico-de-enfermagem"},
        {"name": "Técnico de Informática", "url": "https://www.pciconcursos.com.br/provas/tecnico-de-informatica"},
        {"name": "Técnico de Laboratório", "url": "https://www.pciconcursos.com.br/provas/tecnico-de-laboratorio"},
        {"name": "Técnico de Segurança do Trabalho",
         "url": "https://www.pciconcursos.com.br/provas/tecnico-de-seguranca-do-trabalho"},
        {"name": "Técnico em Radiologia", "url": "https://www.pciconcursos.com.br/provas/tecnico-em-radiologia"},
        {"name": "Técnico em Saúde Bucal", "url": "https://www.pciconcursos.com.br/provas/tecnico-em-saude-bucal"},
        {"name": "Telefonista", "url": "https://www.pciconcursos.com.br/provas/telefonista"},
        {"name": "Terapeuta Ocupacional", "url": "https://www.pciconcursos.com.br/provas/terapeuta-ocupacional"},
        {"name": "Tesoureiro", "url": "https://www.pciconcursos.com.br/provas/tesoureiro"},
        {"name": "Topógrafo", "url": "https://www.pciconcursos.com.br/provas/topografo"},
        {"name": "Tratorista", "url": "https://www.pciconcursos.com.br/provas/tratorista"},
        {"name": "Veterinário", "url": "https://www.pciconcursos.com.br/provas/veterinario"},
        {"name": "Vigia", "url": "https://www.pciconcursos.com.br/provas/vigia"},
        {"name": "Vigilante", "url": "https://www.pciconcursos.com.br/provas/vigilante"},
        {"name": "Zelador", "url": "https://www.pciconcursos.com.br/provas/zelador"}
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()

        for i, cargo_item in enumerate(cargos):
            print(f"\nProcessing CARGO {i + 1}/{len(cargos)}: {cargo_item['name']}")
            process_cargo_page(page, cargo_item["name"], cargo_item["url"], all_exams_data)

            if save_data_to_json(all_exams_data, output_json_file):
                print(f"Progress saved to {output_json_file} after processing {cargo_item['name']}")
            else:
                print(f"Failed to save progress to {output_json_file} after processing {cargo_item['name']}")

            time.sleep(3)

        browser.close()

    if save_data_to_json(all_exams_data, output_json_file):
        print(f"\nAll data successfully saved to {output_json_file}")
    else:
        print(f"\nFailed to save final data to {output_json_file}")

    print("PDF URL extraction completed!")


if __name__ == "__main__":
    main()