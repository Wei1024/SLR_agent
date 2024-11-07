import requests
import time
import json
from dotenv import load_dotenv
import os
import xml.etree.ElementTree as ET
import logging

# Configure logging
logging.basicConfig(
    filename='pubmed_extraction.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Load API key from .env file
load_dotenv()
API_KEY = os.getenv("PUBMED_API_KEY")

def search_pubmed(query: str, batch_size: int = 500) -> set:
    """Searches PubMed with the given query and retrieves all PubMed IDs."""
    logging.info(f"Starting search for query: {query}")
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": batch_size,
        "retmode": "json",
        "usehistory": "y",
        "api_key": API_KEY
    }
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        total_records = int(data["esearchresult"]["count"])
        logging.info(f"Total records found for query: {total_records}")
        webenv = data["esearchresult"]["webenv"]
        query_key = data["esearchresult"]["querykey"]
    except requests.exceptions.RequestException as e:
        logging.error(f"Error during PubMed search: {e}")
        return set()
    
    pmids = set()
    for retstart in range(0, total_records, batch_size):
        logging.info(f"Fetching PubMed IDs {retstart} to {retstart + batch_size}")
        batch_params = {
            "db": "pubmed",
            "query_key": query_key,
            "WebEnv": webenv,
            "retstart": retstart,
            "retmax": batch_size,
            "retmode": "json",
            "api_key": API_KEY
        }
        try:
            batch_response = requests.get(base_url, params=batch_params, timeout=10)
            batch_response.raise_for_status()
            batch_data = batch_response.json()
            batch_pmids = batch_data["esearchresult"]["idlist"]
            pmids.update(batch_pmids)
            logging.info(f"Retrieved {len(batch_pmids)} PubMed IDs")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching PubMed IDs {retstart} to {retstart + batch_size}: {e}")
            continue  # Skip this batch and proceed
        time.sleep(0.3)  # Respect rate limits
    
    logging.info(f"Total unique PubMed IDs collected for query: {len(pmids)}")
    return pmids

def fetch_pubmed_details(pmids: set, batch_size: int = 200) -> list:
    """Fetches detailed information for each PubMed ID in batches and extracts essential fields."""
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    records = []
    pmids = list(pmids)  # Convert to list for batching

    for i in range(0, len(pmids), batch_size):
        batch_ids = ",".join(pmids[i:i + batch_size])
        logging.info(f"Fetching detailed records for PubMed IDs {i + 1} to {i + batch_size}")
        params = {
            "db": "pubmed",
            "id": batch_ids,
            "retmode": "xml",
            "api_key": API_KEY
        }
        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            xml_data = response.text
            records.append(xml_data)
            logging.info(f"Fetched batch {i // batch_size + 1} with {len(pmids[i:i + batch_size])} records")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching details for PubMed IDs {i + 1} to {i + batch_size}: {e}")
            continue  # Skip this batch and proceed
        time.sleep(0.3)  # Respect rate limits

    logging.info(f"Total records fetched: {len(records)} batches")
    return records

def fetch_specific_pmid(pmid: str) -> str:
    """Fetches detailed information for a specific PubMed ID and returns the XML."""
    if not pmid.isdigit():
        logging.warning(f"Invalid PMID format: {pmid}")
        return ""
    
    logging.info(f"Re-attempting fetch for PMID: {pmid}")
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "api_key": API_KEY
    }
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        logging.info(f"Successfully fetched PMID: {pmid}")
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch PMID: {pmid}. Error: {e}")
        return ""

def extract_essential_fields(xml_data: str) -> tuple:
    """
    Parses the XML data and extracts essential fields for all PubMed articles
    (both PubmedArticle and PubmedBookArticle) in the batch.
    
    Returns:
        A tuple containing:
        - List of extracted data dictionaries.
        - Set of processed PMIDs.
    """
    if not xml_data:
        logging.warning("No XML data to parse.")
        return [], set()
    
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        logging.error(f"XML parsing error: {e}")
        return [], set()
    
    # Find both PubmedArticle and PubmedBookArticle elements
    articles = root.findall('.//PubmedArticle') + root.findall('.//PubmedBookArticle')
    
    if not articles:
        # Attempt to extract PMID from XML if no articles found
        pmid = root.findtext('.//PMID')
        if pmid:
            logging.warning(f"No PubmedArticle or PubmedBookArticle found for PMID: {pmid}")
        else:
            logging.warning("No PubmedArticle or PubmedBookArticle found and PMID is missing.")
        return [], set()
    
    extracted_data_list = []
    processed_pmids = set()

    for article in articles:
        try:
            extracted_data = {}
            pmid = None  # Initialize PMID

            if article.tag == 'PubmedArticle':
                # Processing PubmedArticle
                pmid = article.findtext('.//PMID')
                if not pmid:
                    logging.warning("PMID not found in PubmedArticle.")
                    continue  # Skip if PMID is missing
                extracted_data['PMID'] = pmid
                processed_pmids.add(pmid)
                
                # Extract DOI and PMC_ID
                extracted_data['DOI'] = None
                extracted_data['PMC_ID'] = None
                for aid in article.findall('.//ArticleId'):
                    id_type = aid.attrib.get('IdType')
                    if id_type == 'doi' and not extracted_data['DOI']:
                        extracted_data['DOI'] = aid.text
                    elif id_type == 'pmc' and not extracted_data['PMC_ID']:
                        extracted_data['PMC_ID'] = aid.text
                
                # Extract Publication Details
                extracted_data['Title'] = article.findtext('.//ArticleTitle')
                
                journal = article.find('.//Journal')
                if journal is not None:
                    extracted_data['Journal_Title'] = journal.findtext('Title')
                    extracted_data['Journal_ISOAbbreviation'] = journal.findtext('ISOAbbreviation')
                    issn_element = journal.find('.//ISSN')
                    extracted_data['Journal_ISSN'] = issn_element.text if issn_element is not None else None
                else:
                    extracted_data['Journal_Title'] = None
                    extracted_data['Journal_ISOAbbreviation'] = None
                    extracted_data['Journal_ISSN'] = None

                # Publication Date
                pub_date = article.find('.//JournalIssue/PubDate')
                if pub_date is not None:
                    extracted_data['Publication_Year'] = pub_date.findtext('Year')
                    extracted_data['Publication_Month'] = pub_date.findtext('Month')
                    extracted_data['Publication_Day'] = pub_date.findtext('Day')
                else:
                    extracted_data['Publication_Year'] = None
                    extracted_data['Publication_Month'] = None
                    extracted_data['Publication_Day'] = None

                # Volume and Issue
                extracted_data['Volume'] = article.findtext('.//JournalIssue/Volume')
                extracted_data['Issue'] = article.findtext('.//JournalIssue/Issue')

                # Page Numbers
                extracted_data['StartPage'] = article.findtext('.//Pagination/StartPage')
                extracted_data['MedlinePgn'] = article.findtext('.//Pagination/MedlinePgn')

                # Authorship Details
                authors = []
                for author in article.findall('.//AuthorList/Author'):
                    if author.find('LastName') is not None and author.find('ForeName') is not None:
                        author_entry = {
                            'LastName': author.findtext('LastName'),
                            'ForeName': author.findtext('ForeName'),
                            'Initials': author.findtext('Initials'),
                            'Affiliations': [aff.text for aff in author.findall('.//AffiliationInfo/Affiliation') if aff.text]
                        }
                        authors.append(author_entry)
                extracted_data['Authors'] = authors

                # Abstract and Keywords
                abstract = []
                for abstract_text in article.findall('.//Abstract/AbstractText'):
                    label = abstract_text.attrib.get('Label', '')
                    text = abstract_text.text or ''
                    if label:
                        abstract.append(f"{label}: {text}")
                    else:
                        abstract.append(text)
                extracted_data['Abstract'] = "\n".join(abstract)

                # Keywords
                keywords = [kw.text for kw in article.findall('.//KeywordList/Keyword') if kw.text]
                extracted_data['Keywords'] = keywords

                # MeSH Terms
                mesh_terms = []
                for mesh in article.findall('.//MeshHeadingList/MeshHeading'):
                    descriptor = mesh.findtext('DescriptorName')
                    qualifier = mesh.findtext('QualifierName')
                    if qualifier:
                        mesh_terms.append(f"{descriptor} / {qualifier}")
                    else:
                        mesh_terms.append(descriptor)
                extracted_data['MeSH_Terms'] = mesh_terms

                # Publication Type
                publication_types = [pt.text for pt in article.findall('.//PublicationTypeList/PublicationType') if pt.text]
                extracted_data['Publication_Types'] = publication_types

                # Conflict of Interest Statement
                extracted_data['CoiStatement'] = article.findtext('.//CoiStatement')

                # Funding Information
                grants = []
                for grant in article.findall('.//GrantList/Grant'):
                    grant_entry = {
                        'GrantID': grant.findtext('GrantID'),
                        'Agency': grant.findtext('Agency'),
                        'Country': grant.findtext('Country')
                    }
                    grants.append(grant_entry)
                extracted_data['Grants'] = grants if grants else None

                # Full Text Access Information
                if extracted_data['PMC_ID']:
                    extracted_data['Full_Text_URL'] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{extracted_data['PMC_ID']}/"
                elif extracted_data['DOI']:
                    extracted_data['Full_Text_URL'] = f"https://doi.org/{extracted_data['DOI']}"
                else:
                    extracted_data['Full_Text_URL'] = None

                # LinkOut URLs
                linkout_urls = []
                for linkout in article.findall('.//LinkOut'):
                    for link in linkout.findall('.//Url'):
                        if link.text:
                            linkout_urls.append(link.text)
                extracted_data['LinkOut_URLs'] = linkout_urls if linkout_urls else None

                # Publication Status and Language
                extracted_data['Publication_Status'] = article.findtext('.//PubmedData/PublicationStatus')
                extracted_data['Language'] = article.findtext('.//Language')

            elif article.tag == 'PubmedBookArticle':
                # Processing PubmedBookArticle
                book_document = article.find('.//BookDocument')
                if book_document is None:
                    logging.warning("BookDocument not found in PubmedBookArticle.")
                    continue  # Skip if BookDocument is missing

                pmid = book_document.findtext('.//PMID')
                if not pmid:
                    # Sometimes PMID might be in PubmedBookData
                    pmid = article.findtext('.//PubmedBookData/ArticleIdList/ArticleId[@IdType="pubmed"]')
                if not pmid:
                    logging.warning("PMID not found in PubmedBookArticle.")
                    continue  # Skip if PMID is missing
                extracted_data['PMID'] = pmid
                processed_pmids.add(pmid)

                # Extract DOI and PMC_ID
                extracted_data['DOI'] = None
                extracted_data['PMC_ID'] = None
                for aid in book_document.findall('.//ArticleId'):
                    id_type = aid.attrib.get('IdType')
                    if id_type == 'doi' and not extracted_data['DOI']:
                        extracted_data['DOI'] = aid.text
                    elif id_type == 'pmc' and not extracted_data['PMC_ID']:
                        extracted_data['PMC_ID'] = aid.text

                # Extract Publication Details
                extracted_data['Title'] = book_document.findtext('.//BookTitle')
                
                # Book Publisher Information
                book = book_document.find('.//Book')
                if book is not None:
                    publisher = book.find('.//Publisher')
                    if publisher is not None:
                        extracted_data['Journal_Title'] = publisher.findtext('PublisherName')
                        extracted_data['Journal_ISOAbbreviation'] = publisher.findtext('PublisherLocation')
                    else:
                        extracted_data['Journal_Title'] = None
                        extracted_data['Journal_ISOAbbreviation'] = None
                    medium = book.findtext('Medium')
                    extracted_data['Journal_ISSN'] = medium
                else:
                    extracted_data['Journal_Title'] = None
                    extracted_data['Journal_ISOAbbreviation'] = None
                    extracted_data['Journal_ISSN'] = None

                # Publication Date
                pub_date = book_document.find('.//PubDate')
                if pub_date is not None:
                    extracted_data['Publication_Year'] = pub_date.findtext('Year')
                    extracted_data['Publication_Month'] = pub_date.findtext('Month')
                    extracted_data['Publication_Day'] = pub_date.findtext('Day')
                else:
                    extracted_data['Publication_Year'] = None
                    extracted_data['Publication_Month'] = None
                    extracted_data['Publication_Day'] = None

                # Volume and Issue are typically not applicable for Book Articles
                extracted_data['Volume'] = None
                extracted_data['Issue'] = None

                # Page Numbers
                extracted_data['StartPage'] = None
                extracted_data['MedlinePgn'] = None

                # Authorship Details
                authors = []
                for author in book_document.findall('.//AuthorList/Author'):
                    if author.find('LastName') is not None and author.find('ForeName') is not None:
                        author_entry = {
                            'LastName': author.findtext('LastName'),
                            'ForeName': author.findtext('ForeName'),
                            'Initials': author.findtext('Initials'),
                            'Affiliations': [aff.text for aff in author.findall('.//AffiliationInfo/Affiliation') if aff.text]
                        }
                        authors.append(author_entry)
                extracted_data['Authors'] = authors

                # Abstract and Keywords
                abstract = []
                for abstract_text in book_document.findall('.//Abstract/AbstractText'):
                    label = abstract_text.attrib.get('Label', '')
                    text = abstract_text.text or ''
                    if label:
                        abstract.append(f"{label}: {text}")
                    else:
                        abstract.append(text)
                extracted_data['Abstract'] = "\n".join(abstract)

                # Keywords may not be present in Book Articles
                keywords = [kw.text for kw in book_document.findall('.//KeywordList/Keyword') if kw.text]
                extracted_data['Keywords'] = keywords

                # MeSH Terms may not be present in Book Articles
                mesh_terms = []
                for mesh in book_document.findall('.//MeshHeadingList/MeshHeading'):
                    descriptor = mesh.findtext('DescriptorName')
                    qualifier = mesh.findtext('QualifierName')
                    if qualifier:
                        mesh_terms.append(f"{descriptor} / {qualifier}")
                    else:
                        mesh_terms.append(descriptor)
                extracted_data['MeSH_Terms'] = mesh_terms

                # Publication Type
                publication_types = [pt.text for pt in book_document.findall('.//PublicationType') if pt.text]
                extracted_data['Publication_Types'] = publication_types

                # Conflict of Interest Statement may not be present in Book Articles
                extracted_data['CoiStatement'] = book_document.findtext('.//CoiStatement')

                # Funding Information may not be present in Book Articles
                grants = []
                for grant in book_document.findall('.//GrantList/Grant'):
                    grant_entry = {
                        'GrantID': grant.findtext('GrantID'),
                        'Agency': grant.findtext('Agency'),
                        'Country': grant.findtext('Country')
                    }
                    grants.append(grant_entry)
                extracted_data['Grants'] = grants if grants else None

                # Full Text Access Information
                if extracted_data['PMC_ID']:
                    extracted_data['Full_Text_URL'] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{extracted_data['PMC_ID']}/"
                elif extracted_data['DOI']:
                    extracted_data['Full_Text_URL'] = f"https://doi.org/{extracted_data['DOI']}"
                else:
                    extracted_data['Full_Text_URL'] = None

                # LinkOut URLs may not be present in Book Articles
                linkout_urls = []
                for linkout in book_document.findall('.//LinkOut'):
                    for link in linkout.findall('.//Url'):
                        if link.text:
                            linkout_urls.append(link.text)
                extracted_data['LinkOut_URLs'] = linkout_urls if linkout_urls else None

                # Publication Status and Language
                pubmed_book_data = article.find('.//PubmedBookData')
                if pubmed_book_data is not None:
                    extracted_data['Publication_Status'] = pubmed_book_data.findtext('.//PublicationStatus')
                else:
                    extracted_data['Publication_Status'] = None
                extracted_data['Language'] = book_document.findtext('Language')

            else:
                logging.warning(f"Unknown article type: {article.tag}")
                continue  # Skip unknown article types

            # Append the extracted data to the list
            extracted_data_list.append(extracted_data)
            logging.info(f"Successfully extracted data for PMID: {pmid}")

        except Exception as e:
            pmid = article.findtext('.//PMID') or "Unknown PMID"
            logging.error(f"Error extracting data for PMID {pmid}: {e}")
            continue  # Skip to the next article

    return extracted_data_list, processed_pmids

def fetch_specific_pmid_with_retries(pmid: str, retries: int = 3, backoff_factor: float = 0.5) -> str:
    """Fetches detailed information for a specific PubMed ID with retries."""
    for attempt in range(1, retries + 1):
        xml_data = fetch_specific_pmid(pmid)
        if xml_data:
            return xml_data
        else:
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            logging.info(f"Retrying fetch for PMID: {pmid} after {sleep_time} seconds (Attempt {attempt}/{retries})")
            time.sleep(sleep_time)
    logging.error(f"All retry attempts failed for PMID: {pmid}")
    return ""

def save_results_csv(data_list: list, filename="pubmed_results.csv"):
    """Saves the extracted data to a CSV file."""
    import csv

    # Define the order of fields for the CSV, including Full_Text_URL and LinkOut_URLs
    fieldnames = [
        'PMID', 'DOI', 'Full_Text_URL', 'LinkOut_URLs', 'Title', 'Journal_Title', 'Journal_ISOAbbreviation',
        'Journal_ISSN', 'Publication_Year', 'Publication_Month', 'Publication_Day',
        'Volume', 'Issue', 'StartPage', 'MedlinePgn', 'Authors',
        'Abstract', 'Keywords', 'MeSH_Terms', 'Publication_Types',
        'CoiStatement', 'Grants', 'PMC_ID', 'Publication_Status', 'Language'
    ]

    # Open the CSV file in write mode and write the header
    with open(filename, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()

        for data in data_list:
            # Prepare data for CSV
            csv_data = {
                'PMID': data.get('PMID'),
                'DOI': data.get('DOI'),
                'Full_Text_URL': data.get('Full_Text_URL'),
                'LinkOut_URLs': "; ".join(data.get('LinkOut_URLs', [])) if data.get('LinkOut_URLs') else '',
                'Title': data.get('Title'),
                'Journal_Title': data.get('Journal_Title'),
                'Journal_ISOAbbreviation': data.get('Journal_ISOAbbreviation'),
                'Journal_ISSN': data.get('Journal_ISSN'),
                'Publication_Year': data.get('Publication_Year'),
                'Publication_Month': data.get('Publication_Month'),
                'Publication_Day': data.get('Publication_Day'),
                'Volume': data.get('Volume'),
                'Issue': data.get('Issue'),
                'StartPage': data.get('StartPage'),
                'MedlinePgn': data.get('MedlinePgn'),
                'Authors': json.dumps(data.get('Authors'), ensure_ascii=False),
                'Abstract': data.get('Abstract'),
                'Keywords': "; ".join(data.get('Keywords', [])),
                'MeSH_Terms': "; ".join(data.get('MeSH_Terms', [])),
                'Publication_Types': "; ".join(data.get('Publication_Types', [])),
                'CoiStatement': data.get('CoiStatement'),
                'Grants': json.dumps(data.get('Grants'), ensure_ascii=False) if data.get('Grants') else '',
                'PMC_ID': data.get('PMC_ID'),
                'Publication_Status': data.get('Publication_Status'),
                'Language': data.get('Language')
            }

            writer.writerow(csv_data)
    
    logging.info(f"Data saved to {filename}")

def fetch_pubmed_data(query_sets: list, output_filename: str = "pubmed_results.csv"):
    """
    Fetches PubMed data based on a list of query sets and saves the results to a CSV file.

    Parameters:
        query_sets (list): A list of query strings to search PubMed.
        output_filename (str): The name of the CSV file to save the results. Defaults to "pubmed_results.csv".
    """
    # Run searches and combine results
    combined_pmids = set()
    for query in query_sets:
        pmids = search_pubmed(query)
        combined_pmids.update(pmids)

    logging.info(f"Total unique PubMed IDs across all queries: {len(combined_pmids)}")

    # Fetch detailed information for all PubMed IDs
    detailed_records_xml = fetch_pubmed_details(combined_pmids)

    # Initialize a list to hold all extracted data and a set for processed PMIDs
    all_extracted_data = []
    all_processed_pmids = set()

    # Process each batch of XML data
    for xml_data in detailed_records_xml:
        extracted_data_batch, processed_pmids_batch = extract_essential_fields(xml_data)
        all_extracted_data.extend(extracted_data_batch)
        all_processed_pmids.update(processed_pmids_batch)

    # Determine missing PMIDs
    missing_pmids = combined_pmids - all_processed_pmids
    logging.info(f"Total records extracted: {len(all_extracted_data)}")
    logging.info(f"Total PMIDs not processed: {len(missing_pmids)}")
    if missing_pmids:
        logging.warning(f"Missing PMIDs: {', '.join(list(missing_pmids)[:10])}...")  # Show first 10 for brevity
        print(f"\nTotal records extracted: {len(all_extracted_data)}")
        print(f"Total PMIDs not processed: {len(missing_pmids)}")
        print(f"Missing PMIDs saved to missing_pmids.txt")

        # Save missing PMIDs to a separate file for further investigation
        with open("missing_pmids.txt", "w") as f:
            for pmid in missing_pmids:
                f.write(f"{pmid}\n")
        logging.info("Missing PMIDs saved to missing_pmids.txt")
    else:
        logging.info("All PMIDs successfully processed.")
        print("\nAll PMIDs successfully processed.")

    # Re-attempt to fetch missing PMIDs
    if missing_pmids:
        print("\nRe-attempting to fetch missing PMIDs...")
        for pmid in missing_pmids:
            xml_data = fetch_specific_pmid_with_retries(pmid)
            if xml_data:
                extracted_data = extract_essential_fields(xml_data)[0]  # Extracted data list
                if extracted_data:
                    all_extracted_data.extend(extracted_data)
                    all_processed_pmids.add(pmid)
            time.sleep(0.3)  # Respect rate limits

        # Recalculate missing PMIDs after retry
        updated_missing_pmids = combined_pmids - all_processed_pmids
        if updated_missing_pmids:
            logging.error(f"After retry, still missing PMIDs: {len(updated_missing_pmids)}")
            print(f"\nAfter retry, still missing PMIDs: {len(updated_missing_pmids)}")
            print(f"Missing PMIDs saved to still_missing_pmids.txt")
            with open("still_missing_pmids.txt", "w") as f:
                for pmid in updated_missing_pmids:
                    f.write(f"{pmid}\n")
            logging.error("Still missing PMIDs saved to still_missing_pmids.txt")
        else:
            logging.info("All PMIDs successfully processed after retry.")
            print("All PMIDs successfully processed after retry.")

    # Save all extracted data to a CSV file
    save_results_csv(all_extracted_data, filename=output_filename)
    print(f"\nData extraction complete. Results saved to {output_filename}")

# Example usage:
if __name__ == "__main__":
    # Define your query sets as a list of query strings
    QUERY_SETS = [
        "(\"large language model\" OR LLM OR \"GPT-4o\" OR \"Claude 3.5\" OR \"Grok-1\" OR "
        "\"PaLM 2\" OR \"Falcon 180B\" OR \"transformer\" OR \"generative AI\") "
        "AND (\"systematic review\" OR \"literature review\" OR \"evidence synthesis\" OR "
        "\"data extraction\" OR \"information retrieval\")",
        "(\"systematic review automation\" OR \"automated systematic review\" OR "
        "\"AI-assisted literature review\" OR \"data extraction\") "
        "AND (\"health economics\" OR \"outcomes research\" OR pharmacoeconomics OR "
        "\"real-world evidence\")",
        "(\"AI model\" OR \"machine learning\" OR \"deep learning\" OR \"transformer model\" OR "
        "\"BERT\" OR \"large language model\" OR LLM) "
        "AND (\"health economics\" OR \"outcomes research\" OR pharmacoeconomics OR "
        "\"real-world evidence\")"
    ]

    # Call the function with the query sets
    fetch_pubmed_data(QUERY_SETS, output_filename="result_1.csv")
