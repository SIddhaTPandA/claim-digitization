# This file defines the trigger for PDF uploads to the Azure Functions app.

import logging
import azure.functions as func
from src.document_intelligence.pdf_processor import PDFProcessor

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('PDF upload trigger function processed a request.')

    try:
        # Get the PDF file from the request
        pdf_file = req.files['file']
        
        # Process the PDF file
        pdf_processor = PDFProcessor()
        extraction_result = pdf_processor.process(pdf_file)

        # Return a successful response with the extraction result
        return func.HttpResponse(
            body=extraction_result.to_json(),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f'Error processing PDF file: {str(e)}')
        return func.HttpResponse(
            "Error processing PDF file.",
            status_code=500
        )