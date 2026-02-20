# Brief Instructions to Run the Project Locally

## Prerequisites

-   Python 3.11 or 3.12\
-   Azure Functions Core Tools v4\
-   VS Code with Azure Functions Extension\
-   Azurite (local storage emulator)\
-   Azure Storage Explorer (recommended)

## Steps

1.  Clone the repository:

``` bash
git clone <your-repo-url>
cd <repo-folder>
```

2.  Create and activate virtual environment:

``` bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# or
source .venv/bin/activate  # Mac/Linux
```

3.  Install dependencies:

``` bash
pip install -r requirements.txt
```

4.  Configure `local.settings.json`:

``` json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "ImageStorageConnection": "UseDevelopmentStorage=true"
  }
}
```

5.  Start Azurite:

-   VS Code: F1 → "Azurite: Start"
-   Or CLI:

``` bash
azurite
```

6.  Create a Blob container named `images` in the local emulator using
    Azure Storage Explorer.

7.  Run the Function App:

``` bash
func start
```

8.  Upload an image to the `images` container to trigger the Durable
    Function.

9.  View results:

```{=html}
<!-- -->
```
    http://localhost:7071/api/results
