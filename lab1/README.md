# CST8917 – Lab 1: Azure Function Text Analyzer

This project is an Azure Functions application written in Python that analyzes text, stores results in Azure Cosmos DB, and allows retrieving analysis history.

---

## Prerequisites

Before running this project locally, ensure you have:

- **Python 3.12**
- **Azure Functions Core Tools v4**
- **Visual Studio Code**
- **VS Code Extensions:**
  - Azure Functions
  - Python
  - Azurite

---

## Setup Instructions

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt:**
```
azure-functions
azure-cosmos
azure-identity
```

### 2. Configure Local Environment Variables

Use a file named `local.settings.json` in the project root (this file is **not tracked by Git**):

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "COSMOS_ENDPOINT": "https://COSMOS-ACCOUNT.documents.azure.com:443/",
    "COSMOS_KEY": "COSMOS_KEY",
    "COSMOS_DATABASE": "textanalyzerdb",
    "COSMOS_CONTAINER": "analyses"
  }
}
```

**Important Notes:**
- `AzureWebJobsStorage` uses **Azurite** for local storage emulation


---

## Running the Project Locally

### Step 1: Start Azurite

In VS Code:
1. Press `F1` (or `Ctrl+Shift+P`)
2. Type and select: **Azurite: Start**

### Step 2: Start the Azure Function

```bash
func start
```

We should see output indicating your functions are running at `http://localhost:7071`

---

## Testing the Endpoints

### **TextAnalyzer** (Analyze Text)

```bash
curl "http://localhost:7071/api/TextAnalyzer?text=Hello%20world"
```

**Expected Response:**
```json
{
  "id": "abc123...",
  "text": "Hello world",
  "character_count": 11,
  "word_count": 2,
  "sentence_count": 1,
  "timestamp": "2024-02-04T12:34:56.789Z"
}s
```

### **GetAnalysisHistory** (Retrieve Past Analyses)

**Get all history:**
```bash
curl "http://localhost:7071/api/GetAnalysisHistory"
```

**Get limited results:**
```bash
curl "http://localhost:7071/api/GetAnalysisHistory?limit=3"
```

**Expected Response:**
```json
{
  "count": 2,
  "analyses": [
    {
      "id": "abc123...",
      "text": "Hello world",
      "character_count": 11,
      "word_count": 2,
      "sentence_count": 1,
      "timestamp": "2024-02-04T12:34:56.789Z"
    }
  ]
}
```

---

## Author

Ahmed Boudouh – CST8917 Serverless Computing Lab 1
