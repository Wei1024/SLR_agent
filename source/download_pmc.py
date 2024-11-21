import ftplib
import os

# FTP server details
ftp_server = "ftp.ncbi.nlm.nih.gov"
ftp_directory = "/pub/pmc/"
csv_filename = "oa_non_comm_use_pdf.csv"

# Local directory to save the CSV file
local_save_dir = "pmc_csv"
os.makedirs(local_save_dir, exist_ok=True)
local_csv_path = os.path.join(local_save_dir, csv_filename)

# Function to download the CSV file
def download_csv():
    try:
        with ftplib.FTP(ftp_server) as ftp:
            ftp.login()  # Login anonymously
            ftp.cwd(ftp_directory)  # Navigate to the PMC directory

            # List files to confirm the presence of the CSV
            files = ftp.nlst()
            if csv_filename in files:
                # Download the CSV file
                print(f"Downloading {csv_filename}...")
                with open(local_csv_path, "wb") as local_file:
                    ftp.retrbinary(f"RETR {csv_filename}", local_file.write)
                print(f"Downloaded {csv_filename} successfully to {local_csv_path}")
            else:
                print(f"{csv_filename} not found in {ftp_directory}.")
    except Exception as e:
        print(f"Error downloading {csv_filename}: {e}")

# Run the download function
download_csv()
