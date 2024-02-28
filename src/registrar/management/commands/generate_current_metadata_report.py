"""Generates current-metadata.csv then uploads to S3 + sends email"""

import logging
import os
import pyzipper

from django.core.management import BaseCommand
from registrar.utility import csv_export
from registrar.utility.s3_bucket import S3ClientHelper
from ...utility.email import send_templated_email, EmailSendingError


logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = (
        "Generates and uploads a current-metadata.csv file to our S3 bucket " "which is based off of all existing Domains."
    )

    def add_arguments(self, parser):
        """Add our two filename arguments."""
        parser.add_argument("--directory", default="migrationdata", help="Desired directory")
        parser.add_argument(
            "--checkpath",
            default=True,
            help="Flag that determines if we do a check for os.path.exists. Used for test cases",
        )
    
    def handle(self, **options):
        """Grabs the directory then creates current-metadata.csv in that directory"""
        file_name = "current-metadata.csv"
        # Ensures a slash is added
        directory = os.path.join(options.get("directory"), "")
        check_path = options.get("checkpath")

        logger.info("Generating report...")
        try:
            self.generate_current_metadata_report(directory, file_name, check_path)
        except Exception as err:
            # TODO - #1317: Notify operations when auto report generation fails
            raise err
        else:
            logger.info(f"Success! Created {file_name}")

    def generate_current_metadata_report(self, directory, file_name, check_path):
        """Creates a current-full.csv file under the specified directory,
        then uploads it to a AWS S3 bucket"""
        s3_client = S3ClientHelper()
        file_path = os.path.join(directory, file_name)

        # Generate a file locally for upload
        with open(file_path, "w") as file:
            csv_export.export_data_type_to_csv(file)

        if check_path and not os.path.exists(file_path):
            raise FileNotFoundError(f"Could not find newly created file at '{file_path}'")

        # Upload this generated file for our S3 instance
        s3_client.upload_file(file_path, file_name)
        """
        We want to make sure to upload to s3 for back up
        And now we also want to get the file and encrypt it so we can send it in an email
        """
        unencrypted_metadata_input = s3_client.get_file(file_name)


        # Encrypt metadata into a zip file

        # pre-setting zip file name 
        encrypted_metadata_output = 'encrypted_metadata.zip'
        # set this to be an env var somewhere
        password = b'somepasswordhere'
        # encrypted_metadata is the encrypted output
        encrypted_metadata = _encrypt_metadata(unencrypted_metadata_input, encrypted_metadata_output, password)
        print("encrypted_metadata is:", encrypted_metadata)

        # Send the metadata file that is zipped
        # Q: Would we set the vars I set in email.py here to pass in to the helper function or best way to invoke
        # send_templated_email(encrypted_metadata, attachment=True)
    
        def _encrypt_metadata(input_file, output_file, password):
            with open(input_file, 'rb') as f_in:
                with pyzipper.AESZipFile(output_file, 'w', compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES) as f_out:
                    f_out.setpassword(password)
                    f_out.writestr(input_file, f_in.read())
            return output_file
