# SPD Benefits Extraction

## Overview
The SPD Benefits Extraction project is an Azure-native Intelligent Document Processing solution designed to extract healthcare benefits data from two-tier network SPD/SBC PDF documents. The extracted data is then outputted in a standardized Excel format, facilitating easier analysis and reporting.

## Project Structure
The project is organized into several key directories:

- **src/**: Contains the main application code, including agents, document intelligence, validators, ontology, generators, services, models, and utility functions.
- **functions/**: Contains Azure Functions that handle triggers for PDF uploads, orchestration, and human review.
- **tests/**: Contains unit and integration tests to ensure the reliability and correctness of the application.
- **infra/**: Contains infrastructure as code files for deploying Azure resources using Bicep.
- **data/**: Contains data files, such as the master service list in JSON format.
- **.env.example**: Provides an example of environment variables for the application.
- **requirements.txt**: Lists the production dependencies for the project.
- **README.md**: This file.

## Getting Started

### Prerequisites
- Python 3.8 or higher
- Azure account with access to Azure Functions, Blob Storage, Service Bus, SQL Database, and Key Vault
- Required Python packages (see `requirements.txt`)

### Installation
1. Clone the repository:
   ```
   git clone <repository-url>
   cd spd-benefits-extraction
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

### Configuration
- Copy `.env.example` to `.env` and fill in the necessary environment variables.
- Update `src/config/settings.py` with your Azure service endpoints and other configuration settings.

### Running the Application
To run the application, execute the following command:
```
python src/main.py
```

### Deploying to Azure
Use the Bicep files in the `infra/` directory to deploy the necessary Azure resources. Ensure you have the Azure CLI installed and configured.

## Testing
To run the tests, use the following command:
```
pytest tests/
```

## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for details.