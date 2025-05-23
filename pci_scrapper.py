"""
Browser-based PDF URL Extractor for PCIConcursos

This script extracts PDF URLs from exam detail pages on PCIConcursos.com.br
using browser automation with Playwright.

Requirements:
- Python 3.6+
- playwright
- beautifulsoup4
- requests

Installation:
pip install playwright beautifulsoup4 requests
playwright install

Usage:
python pci_scrapper.py
"""

import json
import os
import time
import re
from playwright.sync_api import sync_playwright

# Function to extract PDF URLs from an exam detail page
def extract_pdf_urls(page, exam_url):
    print(f"Extracting PDF URLs from {exam_url}")
    
    # Navigate to the exam detail page
    page.goto(exam_url, wait_until="networkidle")
    
    # Execute JavaScript to extract PDF URLs
    pdf_links = page.evaluate("""() => {
        // Extract PDF URLs from the page
        const pdfLinks = [];
        const allLinks = document.querySelectorAll("a");

        // Look for links with "Baixar" text that point to PDF files
        for (const link of allLinks) {
            if (link.textContent.includes("Baixar")) {
                // Get the actual href attribute
                const href = link.getAttribute("href");
                if (href && href.includes(".pdf")) {
                    // Fix the URL to avoid duplication of domain
                    if (href.startsWith("http")) {
                        pdfLinks.push(href);
                    } else {
                        pdfLinks.push(window.location.origin + href);
                    }
                }
            }
        }

        // If no links found with "Baixar", try to get all PDF links
        if (pdfLinks.length === 0) {
            for (const link of allLinks) {
                const href = link.getAttribute("href");
                if (href && href.includes(".pdf")) {
                    // Fix the URL to avoid duplication of domain
                    if (href.startsWith("http")) {
                        pdfLinks.push(href);
                    } else {
                        pdfLinks.push(window.location.origin + href);
                    }
                }
            }
        }

        // Remove duplicates
        return [...new Set(pdfLinks)];
    }""")
    
    return pdf_links

# MODIFIED Function to update exam data with PDF URLs
def update_exam_with_pdf_urls(cargo_name, exam_details_from_link, pdf_urls_found):
    # Convert cargo name to filename format - handle special characters properly
    cargo_filename = cargo_name.lower()
    cargo_filename = cargo_filename.replace("ã", "a").replace("á", "a").replace("â", "a")
    cargo_filename = cargo_filename.replace("é", "e").replace("ê", "e")
    cargo_filename = cargo_filename.replace("í", "i")
    cargo_filename = cargo_filename.replace("ó", "o").replace("ô", "o")
    cargo_filename = cargo_filename.replace("ú", "u")
    cargo_filename = cargo_filename.replace("ç", "c")
    cargo_filename = cargo_filename.replace(" ", "_").replace("-", "_").replace("/", "_").replace("\\", "_")
    
    json_file = f"{cargo_filename}_exams.json"
    
    exams_list = []
    try:
        # Load existing exam data if file exists
        with open(json_file, "r", encoding="utf-8") as f:
            exams_list = json.load(f)
        # Ensure the loaded data is a list
        if not isinstance(exams_list, list):
            print(f"Warning: Content of {json_file} was not a list. Reinitializing.")
            exams_list = []
    except FileNotFoundError:
        print(f"{json_file} not found. A new file will be created.")
        # exams_list is already initialized as an empty list
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {json_file}. File content will be replaced/reinitialized.")
        exams_list = [] # Reset to empty list if file is corrupt
    except Exception as e:
        print(f"An unexpected error occurred while loading {json_file}: {e}. File will be reinitialized.")
        exams_list = []

    # Key for the current exam being processed (using lowercase keys from exam_details_from_link)
    # exam_details_from_link contains: 'position', 'agency', 'year', 'url', 'organizer', 'level'
    current_exam_key = f"{exam_details_from_link.get('position','')} - {exam_details_from_link.get('agency','')} - {exam_details_from_link.get('year','')}"
    
    exam_found_in_file = False
    for exam_in_list in exams_list:
        # Construct key from exam_in_list, assuming it also uses lowercase keys
        key_from_file_exam = f"{exam_in_list.get('position','')} - {exam_in_list.get('agency','')} - {exam_in_list.get('year','')}"
        if key_from_file_exam == current_exam_key:
            # Update existing exam entry
            exam_in_list.update(exam_details_from_link) # Update with all current details
            exam_in_list['PdfUrls'] = pdf_urls_found    # Set/update PDF URLs
            exam_found_in_file = True
            print(f"Updated {current_exam_key} in {json_file}")
            break
            
    if not exam_found_in_file:
        # Exam not found, so add it as a new entry
        new_exam_entry = exam_details_from_link.copy() # Copy all details
        new_exam_entry['PdfUrls'] = pdf_urls_found     # Add PDF URLs
        exams_list.append(new_exam_entry)
        print(f"Added new entry for {current_exam_key} to {json_file}")

    try:
        # Save the updated list back to the JSON file
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(exams_list, f, ensure_ascii=False, indent=2)
        # print(f"Successfully saved data to {json_file}") # Optional: for more verbose logging
        return True
    except Exception as e:
        print(f"Error saving updated data to {json_file}: {e}")
        return False

# Function to extract exam links from a cargo page
def extract_exam_links(page, cargo_url):
    print(f"Extracting exam links from {cargo_url}")
    
    # Navigate to the cargo page
    page.goto(cargo_url, wait_until="networkidle")
    
    # Execute JavaScript to extract exam links
    exam_links = page.evaluate("""() => {
        // Extract exam links from the table
        const examLinks = [];
        const rows = document.querySelectorAll("table tr");
        
        for (let i = 1; i < rows.length; i++) { // Skip header row
            const row = rows[i];
            const firstCell = row.querySelector("td:first-child");
            if (firstCell) {
                const link = firstCell.querySelector("a");
                if (link && link.href) {
                    examLinks.push({
                        url: link.href,
                        position: link.textContent.trim(),
                        year: row.querySelector("td:nth-child(2)") ? row.querySelector("td:nth-child(2)").textContent.trim() : "",
                        agency: row.querySelector("td:nth-child(3) a") ? row.querySelector("td:nth-child(3) a").textContent.trim() : "",
                        organizer: row.querySelector("td:nth-child(4) a") ? row.querySelector("td:nth-child(4) a").textContent.trim() : "",
                        level: row.querySelector("td:nth-child(5)") ? row.querySelector("td:nth-child(5)").textContent.trim() : ""
                    });
                }
            }
        }
        
        return examLinks;
    }""")
    
    return exam_links

# MODIFIED process_cargo function
def process_cargo(page, cargo_name, cargo_url):
    print(f"Processing cargo: {cargo_name} at {cargo_url}")
    
    # Load existing PDF URLs data if available (for the master list)
    pdf_urls_file = "exam_pdf_urls.json"
    if os.path.exists(pdf_urls_file):
        try:
            with open(pdf_urls_file, "r", encoding="utf-8") as f:
                exam_pdf_urls = json.load(f)
            if not isinstance(exam_pdf_urls, dict): # Ensure it's a dictionary
                print(f"Warning: {pdf_urls_file} did not contain a dictionary. Reinitializing.")
                exam_pdf_urls = {}
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {pdf_urls_file}. Reinitializing master PDF URL list.")
            exam_pdf_urls = {}
        except Exception as e:
            print(f"An unexpected error occurred loading {pdf_urls_file}: {e}. Reinitializing master PDF URL list.")
            exam_pdf_urls = {}
    else:
        exam_pdf_urls = {}
    
    # Extract exam links from the cargo page
    # exam_link_list will be a list of dictionaries, e.g., [{'url': ..., 'position': ..., 'year': ..., ...}, ...]
    exam_link_list = extract_exam_links(page, cargo_url)
    print(f"Found {len(exam_link_list)} exam links for {cargo_name}")
    
    # Process each exam link
    for i, exam_link_details in enumerate(exam_link_list):
        # exam_link_details is a dictionary with keys: 'url', 'position', 'year', 'agency', 'organizer', 'level'
        # These keys are lowercase as returned by the JavaScript in extract_exam_links
        
        print(f"Processing exam {i+1}/{len(exam_link_list)}: {exam_link_details.get('position','N/A')} - {exam_link_details.get('agency','N/A')} - {exam_link_details.get('year','N/A')}")
        
        # Create a key for the exam for the master list (exam_pdf_urls)
        # Ensure consistency by using lowercase keys from exam_link_details
        exam_key = f"{exam_link_details.get('position','')} - {exam_link_details.get('agency','')} - {exam_link_details.get('year','')}"
        
        # Check if we already have PDF URLs for this exam in the master list
        if exam_key in exam_pdf_urls:
            print(f"Already have PDF URLs for {exam_key} in master list.")
            # Optionally, you might still want to call update_exam_with_pdf_urls
            # if the cargo-specific JSON could be missing or outdated,
            # and you have the pdf_urls from exam_pdf_urls[exam_key].
            # For this example, we'll skip to avoid re-processing if already in master.
            # However, to ensure cargo-specific files are robustly populated even if master exists,
            # one might pass exam_pdf_urls[exam_key] to update_exam_with_pdf_urls here.
            # For now, let's keep the original skip logic for the master list.
            # If you want to ensure the cargo-specific file is updated even if master key exists:
            # pdf_urls_from_master = exam_pdf_urls.get(exam_key)
            # if pdf_urls_from_master:
            #     update_exam_with_pdf_urls(cargo_name, exam_link_details, pdf_urls_from_master)
            continue # Skip to next exam if already processed for master list
        
        # Extract PDF URLs from the exam detail page
        pdf_urls = extract_pdf_urls(page, exam_link_details["url"])
        
        if pdf_urls:
            # Add PDF URLs to our master data
            exam_pdf_urls[exam_key] = pdf_urls
            print(f"Added {len(pdf_urls)} PDF URLs for {exam_key} to master list.")
            
            # Update the exam data in the cargo-specific JSON file
            # Pass the full exam_link_details dictionary
            update_exam_with_pdf_urls(cargo_name, exam_link_details, pdf_urls)
        else:
            print(f"No PDF URLs found for {exam_key}")
        
        # Save PDF URLs master data after each exam to avoid losing progress
        try:
            with open(pdf_urls_file, "w", encoding="utf-8") as f:
                json.dump(exam_pdf_urls, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving master PDF URL list to {pdf_urls_file}: {e}")

        # Add a small delay to avoid overloading the server
        time.sleep(2)
    
    print(f"Completed processing {cargo_name}")
    return True

# Main function to process all cargos
def main():
    # List of ALL cargos from PCIConcursos provas page
    cargos = [
        {"name": "Administração", "url": "https://www.pciconcursos.com.br/provas/administracao"},
        {"name": "Administrador", "url": "https://www.pciconcursos.com.br/provas/administrador"},
        {"name": "Administrador Hospitalar", "url": "https://www.pciconcursos.com.br/provas/administrador-hospitalar"},
        # ... (the rest of your cargos list remains the same)
        {"name": "Administrador Júnior", "url": "https://www.pciconcursos.com.br/provas/administrador-junior"},
        {"name": "Advogado", "url": "https://www.pciconcursos.com.br/provas/advogado"},
        {"name": "Advogado Júnior", "url": "https://www.pciconcursos.com.br/provas/advogado-junior"},
        {"name": "Agente Administrativo", "url": "https://www.pciconcursos.com.br/provas/agente-administrativo"},
        {"name": "Agente Administrativo I", "url": "https://www.pciconcursos.com.br/provas/agente-administrativo-i"},
        {"name": "Agente Comunitário de Saúde", "url": "https://www.pciconcursos.com.br/provas/agente-comunitario-de-saude"},
        {"name": "Agente de Combate as Endemias", "url": "https://www.pciconcursos.com.br/provas/agente-de-combate-as-endemias"},
        {"name": "Agente de Defesa Civil", "url": "https://www.pciconcursos.com.br/provas/agente-de-defesa-civil"},
        {"name": "Agente de Endemias", "url": "https://www.pciconcursos.com.br/provas/agente-de-endemias"},
        {"name": "Agente de Fiscalização", "url": "https://www.pciconcursos.com.br/provas/agente-de-fiscalizacao"},
        {"name": "Agente de Polícia", "url": "https://www.pciconcursos.com.br/provas/agente-de-policia"},
        {"name": "Agente de Portaria", "url": "https://www.pciconcursos.com.br/provas/agente-de-portaria"},
        {"name": "Agente de Saúde", "url": "https://www.pciconcursos.com.br/provas/agente-de-saude"},
        {"name": "Agente de Serviços Gerais", "url": "https://www.pciconcursos.com.br/provas/agente-de-servicos-gerais"},
        {"name": "Agente de Trânsito", "url": "https://www.pciconcursos.com.br/provas/agente-de-transito"},
        {"name": "Agente de Vigilância Sanitária", "url": "https://www.pciconcursos.com.br/provas/agente-de-vigilancia-sanitaria"},
        {"name": "Agente Fiscal", "url": "https://www.pciconcursos.com.br/provas/agente-fiscal"},
        {"name": "Agente Municipal de Trânsito", "url": "https://www.pciconcursos.com.br/provas/agente-municipal-de-transito"},
        {"name": "Agente Operacional", "url": "https://www.pciconcursos.com.br/provas/agente-operacional"},
        {"name": "Agente Penitenciário", "url": "https://www.pciconcursos.com.br/provas/agente-penitenciario"},
        {"name": "Agente Social", "url": "https://www.pciconcursos.com.br/provas/agente-social"},
        {"name": "Almoxarife", "url": "https://www.pciconcursos.com.br/provas/almoxarife"},
        {"name": "Analista Administrativo", "url": "https://www.pciconcursos.com.br/provas/analista-administrativo"},
        {"name": "Analista Ambiental", "url": "https://www.pciconcursos.com.br/provas/analista-ambiental"},
        {"name": "Analista Contábil", "url": "https://www.pciconcursos.com.br/provas/analista-contabil"},
        {"name": "Analista de Controle Interno", "url": "https://www.pciconcursos.com.br/provas/analista-de-controle-interno"},
        {"name": "Analista de Informática", "url": "https://www.pciconcursos.com.br/provas/analista-de-informatica"},
        {"name": "Analista de Recursos Humanos", "url": "https://www.pciconcursos.com.br/provas/analista-de-recursos-humanos"},
        {"name": "Analista de Sistema", "url": "https://www.pciconcursos.com.br/provas/analista-de-sistema"},
        {"name": "Analista de Sistemas", "url": "https://www.pciconcursos.com.br/provas/analista-de-sistemas"},
        {"name": "Analista de Suporte", "url": "https://www.pciconcursos.com.br/provas/analista-de-suporte"},
        {"name": "Analista de Tecnologia da Informação", "url": "https://www.pciconcursos.com.br/provas/analista-de-tecnologia-da-informacao"},
        {"name": "Analista Financeiro", "url": "https://www.pciconcursos.com.br/provas/analista-financeiro"},
        {"name": "Analista Judiciário - Administrativa", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-administrativa"},
        {"name": "Analista Judiciário - Análise de Sistemas", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-analise-de-sistemas"},
        {"name": "Analista Judiciário - Arquitetura", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-arquitetura"},
        {"name": "Analista Judiciário - Arquivologia", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-arquivologia"},
        {"name": "Analista Judiciário - Assistente Social", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-assistente-social"},
        {"name": "Analista Judiciário - Biblioteconomia", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-biblioteconomia"},
        {"name": "Analista Judiciário - Contabilidade", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-contabilidade"},
        {"name": "Analista Judiciário - Engenharia Civil", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-engenharia-civil"},
        {"name": "Analista Judiciário - Engenharia Elétrica", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-engenharia-eletrica"},
        {"name": "Analista Judiciário - Estatística", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-estatistica"},
        {"name": "Analista Judiciário - Execução de Mandados", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-execucao-de-mandados"},
        {"name": "Analista Judiciário - Medicina", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-medicina"},
        {"name": "Analista Judiciário - Odontologia", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-odontologia"},
        {"name": "Analista Judiciário - Psicologia", "url": "https://www.pciconcursos.com.br/provas/analista-judiciario-psicologia"},
        {"name": "Analista Jurídico", "url": "https://www.pciconcursos.com.br/provas/analista-juridico"},
        {"name": "Arquiteto", "url": "https://www.pciconcursos.com.br/provas/arquiteto"},
        {"name": "Arquiteto e Urbanista", "url": "https://www.pciconcursos.com.br/provas/arquiteto-e-urbanista"},
        {"name": "Arquivista", "url": "https://www.pciconcursos.com.br/provas/arquivista"},
        {"name": "Arquivologista", "url": "https://www.pciconcursos.com.br/provas/arquivologista"},
        {"name": "Assessor Jurídico", "url": "https://www.pciconcursos.com.br/provas/assessor-juridico"},
        {"name": "Assistente Administrativo", "url": "https://www.pciconcursos.com.br/provas/assistente-administrativo"},
        {"name": "Assistente Administrativo I", "url": "https://www.pciconcursos.com.br/provas/assistente-administrativo-i"},
        {"name": "Assistente de Administração", "url": "https://www.pciconcursos.com.br/provas/assistente-de-administracao"},
        {"name": "Assistente de Alunos", "url": "https://www.pciconcursos.com.br/provas/assistente-de-alunos"},
        {"name": "Assistente de Informática", "url": "https://www.pciconcursos.com.br/provas/assistente-de-informatica"},
        {"name": "Assistente de Laboratório", "url": "https://www.pciconcursos.com.br/provas/assistente-de-laboratorio"},
        {"name": "Assistente em Administração", "url": "https://www.pciconcursos.com.br/provas/assistente-em-administracao"},
        {"name": "Assistente Jurídico", "url": "https://www.pciconcursos.com.br/provas/assistente-juridico"},
        {"name": "Assistente Legislativo", "url": "https://www.pciconcursos.com.br/provas/assistente-legislativo"},
        {"name": "Assistente Social", "url": "https://www.pciconcursos.com.br/provas/assistente-social"},
        {"name": "Assistente Técnico", "url": "https://www.pciconcursos.com.br/provas/assistente-tecnico"},
        {"name": "Assistente Técnico Administrativo", "url": "https://www.pciconcursos.com.br/provas/assistente-tecnico-administrativo"},
        {"name": "Atendente", "url": "https://www.pciconcursos.com.br/provas/atendente"},
        {"name": "Atendente de Consultório Dentário", "url": "https://www.pciconcursos.com.br/provas/atendente-de-consultorio-dentario"},
        {"name": "Atendente de Farmácia", "url": "https://www.pciconcursos.com.br/provas/atendente-de-farmacia"},
        {"name": "Auditor", "url": "https://www.pciconcursos.com.br/provas/auditor"},
        {"name": "Auditor Fiscal", "url": "https://www.pciconcursos.com.br/provas/auditor-fiscal"},
        {"name": "Auxiliar Administrativo", "url": "https://www.pciconcursos.com.br/provas/auxiliar-administrativo"},
        {"name": "Auxiliar de Administração", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-administracao"},
        {"name": "Auxiliar de Almoxarifado", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-almoxarifado"},
        {"name": "Auxiliar de Biblioteca", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-biblioteca"},
        {"name": "Auxiliar de Consultório Dentário", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-consultorio-dentario"},
        {"name": "Auxiliar de Consultório Odontológico", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-consultorio-odontologico"},
        {"name": "Auxiliar de Contabilidade", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-contabilidade"},
        {"name": "Auxiliar de Cozinha", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-cozinha"},
        {"name": "Auxiliar de Creche", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-creche"},
        {"name": "Auxiliar de Dentista", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-dentista"},
        {"name": "Auxiliar de Enfermagem", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-enfermagem"},
        {"name": "Auxiliar de Enfermagem do Trabalho", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-enfermagem-do-trabalho"},
        {"name": "Auxiliar de Farmácia", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-farmacia"},
        {"name": "Auxiliar de Laboratório", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-laboratorio"},
        {"name": "Auxiliar de Manutenção", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-manutencao"},
        {"name": "Auxiliar de Mecânico", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-mecanico"},
        {"name": "Auxiliar de Odontologia", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-odontologia"},
        {"name": "Auxiliar de Saúde Bucal", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-saude-bucal"},
        {"name": "Auxiliar de Secretária", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-secretaria"},
        {"name": "Auxiliar de Secretária Escolar", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-secretaria-escolar"},
        {"name": "Auxiliar de Serviços", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-servicos"},
        {"name": "Auxiliar de Serviços Gerais", "url": "https://www.pciconcursos.com.br/provas/auxiliar-de-servicos-gerais"},
        {"name": "Auxiliar em Administração", "url": "https://www.pciconcursos.com.br/provas/auxiliar-em-administracao"},
        {"name": "Auxiliar em Enfermagem", "url": "https://www.pciconcursos.com.br/provas/auxiliar-em-enfermagem"},
        {"name": "Auxiliar em Saúde Bucal", "url": "https://www.pciconcursos.com.br/provas/auxiliar-em-saude-bucal"},
        {"name": "Auxiliar Odontológico", "url": "https://www.pciconcursos.com.br/provas/auxiliar-odontologico"},
        {"name": "Auxiliar Operacional", "url": "https://www.pciconcursos.com.br/provas/auxiliar-operacional"},
        {"name": "Bibliotecário", "url": "https://www.pciconcursos.com.br/provas/bibliotecario"},
        {"name": "Bibliotecário-Documentalista", "url": "https://www.pciconcursos.com.br/provas/bibliotecario-documentalista"},
        {"name": "Biblioteconomista", "url": "https://www.pciconcursos.com.br/provas/biblioteconomista"},
        {"name": "Biólogo", "url": "https://www.pciconcursos.com.br/provas/biologo"},
        {"name": "Biomédico", "url": "https://www.pciconcursos.com.br/provas/biomedico"},
        {"name": "Bioquímico", "url": "https://www.pciconcursos.com.br/provas/bioquimico"},
        {"name": "Bombeiro", "url": "https://www.pciconcursos.com.br/provas/bombeiro"},
        {"name": "Bombeiro Hidráulico", "url": "https://www.pciconcursos.com.br/provas/bombeiro-hidraulico"},
        {"name": "Borracheiro", "url": "https://www.pciconcursos.com.br/provas/borracheiro"},
        {"name": "Calceteiro", "url": "https://www.pciconcursos.com.br/provas/calceteiro"},
        {"name": "Cargos Ensino Fundamental", "url": "https://www.pciconcursos.com.br/provas/cargos-ensino-fundamental"},
        {"name": "Cargos Ensino Fundamental Completo", "url": "https://www.pciconcursos.com.br/provas/cargos-ensino-fundamental-completo"},
        {"name": "Cargos Ensino Fundamental Incompleto", "url": "https://www.pciconcursos.com.br/provas/cargos-ensino-fundamental-incompleto"},
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
        {"name": "Engenheiro de Producão", "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-producao"},
        {"name": "Engenheiro de Segurança do Trabalho", "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-seguranca-do-trabalho"},
        {"name": "Engenheiro de Telecomunicações", "url": "https://www.pciconcursos.com.br/provas/engenheiro-de-telecomunicacoes"},
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
        {"name": "Fiscal de Obras e Posturas", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-obras-e-posturas"},
        {"name": "Fiscal de Posturas", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-posturas"},
        {"name": "Fiscal de Tributos", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-tributos"},
        {"name": "Fiscal de Vigilância Sanitária", "url": "https://www.pciconcursos.com.br/provas/fiscal-de-vigilancia-sanitaria"},
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
        {"name": "Juiz do Trabalho Substituto", "url": "https://www.pciconcursos.com.br/provas/juiz-do-trabalho-substituto"},
        {"name": "Juiz Federal Substituto", "url": "https://www.pciconcursos.com.br/provas/juiz-federal-substituto"},
        {"name": "Juiz Substituto", "url": "https://www.pciconcursos.com.br/provas/juiz-substituto"},
        {"name": "Marceneiro", "url": "https://www.pciconcursos.com.br/provas/marceneiro"},
        {"name": "Mecânico", "url": "https://www.pciconcursos.com.br/provas/mecanico"},
        {"name": "Médico", "url": "https://www.pciconcursos.com.br/provas/medico"},
        {"name": "Médico - Cardiologia", "url": "https://www.pciconcursos.com.br/provas/medico-cardiologia"},
        {"name": "Médico - Cirurgia Geral", "url": "https://www.pciconcursos.com.br/provas/medico-cirurgia-geral"},
        {"name": "Médico - Cirurgia Pediátrica", "url": "https://www.pciconcursos.com.br/provas/medico-cirurgia-pediatrica"},
        {"name": "Médico Clínica Médica", "url": "https://www.pciconcursos.com.br/provas/medico-clinica-medica"},
        {"name": "Médico - Dermatologia", "url": "https://www.pciconcursos.com.br/provas/medico-dermatologia"},
        {"name": "Médico - Endocrinologia", "url": "https://www.pciconcursos.com.br/provas/medico-endocrinologia"},
        {"name": "Médico - Medicina do Trabalho", "url": "https://www.pciconcursos.com.br/provas/medico-medicina-do-trabalho"},
        {"name": "Médico - Neurocirurgia", "url": "https://www.pciconcursos.com.br/provas/medico-neurocirurgia"},
        {"name": "Médico - Neurologia", "url": "https://www.pciconcursos.com.br/provas/medico-neurologia"},
        {"name": "Médico - Oftalmologia", "url": "https://www.pciconcursos.com.br/provas/medico-oftalmologia"},
        {"name": "Médico - Otorrinolaringologia", "url": "https://www.pciconcursos.com.br/provas/medico-otorrinolaringologia"},
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
        {"name": "Médico Ginecologista e Obstetra", "url": "https://www.pciconcursos.com.br/provas/medico-ginecologista-e-obstetra"},
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
        {"name": "Motorista de Veículos Leves", "url": "https://www.pciconcursos.com.br/provas/motorista-de-veiculos-leves"},
        {"name": "Motorista de Veículos Pesados", "url": "https://www.pciconcursos.com.br/provas/motorista-de-veiculos-pesados"},
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
        {"name": "Operador de máquinas agrícolas", "url": "https://www.pciconcursos.com.br/provas/operador-de-maquinas-agricolas"},
        {"name": "Operador de Máquinas Pesadas", "url": "https://www.pciconcursos.com.br/provas/operador-de-maquinas-pesadas"},
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
        {"name": "Professor - Educação Física", "url": "https://www.pciconcursos.com.br/provas/professor-educacao-fisica"},
        {"name": "Professor Educação Infantil", "url": "https://www.pciconcursos.com.br/provas/professor-educacao-infantil"},
        {"name": "Professor - Ensino Religioso", "url": "https://www.pciconcursos.com.br/provas/professor-ensino-religioso"},
        {"name": "Professor - Espanhol", "url": "https://www.pciconcursos.com.br/provas/professor-espanhol"},
        {"name": "Professor - Física", "url": "https://www.pciconcursos.com.br/provas/professor-fisica"},
        {"name": "Professor - Geografia", "url": "https://www.pciconcursos.com.br/provas/professor-geografia"},
        {"name": "Professor - História", "url": "https://www.pciconcursos.com.br/provas/professor-historia"},
        {"name": "Professor - Informática", "url": "https://www.pciconcursos.com.br/provas/professor-informatica"},
        {"name": "Professor - Inglês", "url": "https://www.pciconcursos.com.br/provas/professor-ingles"},
        {"name": "Professor - Língua Inglesa", "url": "https://www.pciconcursos.com.br/provas/professor-lingua-inglesa"},
        {"name": "Professor - Língua Portuguesa", "url": "https://www.pciconcursos.com.br/provas/professor-lingua-portuguesa"},
        {"name": "Professor - Matemática", "url": "https://www.pciconcursos.com.br/provas/professor-matematica"},
        {"name": "Professor - Português", "url": "https://www.pciconcursos.com.br/provas/professor-portugues"},
        {"name": "Professor - Química", "url": "https://www.pciconcursos.com.br/provas/professor-quimica"},
        {"name": "Professor - Séries Iniciais", "url": "https://www.pciconcursos.com.br/provas/professor-series-iniciais"},
        {"name": "Professor de 1ª a 4ª séries", "url": "https://www.pciconcursos.com.br/provas/professor-de-1-a-4-series"},
        {"name": "Professor de Arte", "url": "https://www.pciconcursos.com.br/provas/professor-de-arte"},
        {"name": "Professor de Artes", "url": "https://www.pciconcursos.com.br/provas/professor-de-artes"},
        {"name": "Professor de Biologia", "url": "https://www.pciconcursos.com.br/provas/professor-de-biologia"},
        {"name": "Professor de Ciências", "url": "https://www.pciconcursos.com.br/provas/professor-de-ciencias"},
        {"name": "Professor de Educação Artística", "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-artistica"},
        {"name": "Professor de Educação Básica", "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-basica"},
        {"name": "Professor de Educação Básica I", "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-basica-i"},
        {"name": "Professor de Educação Básica II - Matemática", "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-basica-ii-matematica"},
        {"name": "Professor de Educação Especial", "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-especial"},
        {"name": "Professor de Educação Física", "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-fisica"},
        {"name": "Professor de Educação Infantil", "url": "https://www.pciconcursos.com.br/provas/professor-de-educacao-infantil"},
        {"name": "Professor de Ensino Fundamental", "url": "https://www.pciconcursos.com.br/provas/professor-de-ensino-fundamental"},
        {"name": "Professor de Ensino Religioso", "url": "https://www.pciconcursos.com.br/provas/professor-de-ensino-religioso"},
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
        {"name": "Programador de Computador", "url": "https://www.pciconcursos.com.br/provas/programador-de-computador"},
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
        {"name": "Técnico de Segurança do Trabalho", "url": "https://www.pciconcursos.com.br/provas/tecnico-de-seguranca-do-trabalho"},
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
        browser = playwright.chromium.launch(headless=True) # Set to False to see browser UI
        context = browser.new_context()
        page = context.new_page()
        
        # Process each cargo
        for i, cargo in enumerate(cargos):
            print(f"Processing cargo {i+1}/{len(cargos)}: {cargo['name']}")
            process_cargo(page, cargo["name"], cargo["url"])
            
            # Add a small delay to avoid overloading the server
            time.sleep(3) # Delay between processing different cargos
        
        browser.close()
    
    print("PDF URL extraction completed!")

if __name__ == "__main__":
    main()
    