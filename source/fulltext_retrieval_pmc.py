import requests
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def download_pmc_pdfs(pmc_ids, output_dir, delay=0.2):
    # Get the API key from environment variables
    api_key = os.getenv("PUBMED_API_KEY")
    if not api_key:
        print("API key not found in environment variables.")
        return

    # Headers to mimic a browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.183 Safari/537.36"
    }

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Loop through each PMC ID and download the PDF
    for pmc_id in pmc_ids:
        # Clean and format PMC ID
        pmc_id = pmc_id.strip()
        base_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
        params = {"api_key": api_key}
        
        try:
            # Send GET request to download PDF
            response = requests.get(base_url, headers=headers, params=params)
            response.raise_for_status()  # Check if the request was successful

            # Define output path for each PDF
            output_path = os.path.join(output_dir, f"{pmc_id}.pdf")
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(response.content)
            
            print(f"Downloaded PDF for {pmc_id} and saved as {output_path}")

        except requests.exceptions.HTTPError as e:
            print(f"Error downloading PDF for {pmc_id}: {e}")

        # Respect the rate limit by sleeping
        time.sleep(delay)

# Example usage
pmc_ids =pmc_ids = [
    "PMC10040366",
    "PMC4006759",
    "PMC10951032",
    "PMC11425943",
    "PMC10900550",
    "PMC6563572",
    "PMC9031427",
    "PMC9024015",
    "PMC9582972"
]

output_dir = "pmc_pdfs"
download_pmc_pdfs(pmc_ids, output_dir, delay=0.2)  # Adjust delay as per your rate limit
