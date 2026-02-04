# =============================================================================
# IMPORTS - Libraries we need for our function
# =============================================================================
import azure.functions as func  # Azure Functions SDK - required for all Azure Functions
import logging  # Built-in Python library for printing log messages
import json  # Built-in Python library for working with JSON data
import re  # Built-in Python library for Regular Expressions (pattern matching)
from datetime import (
    datetime,
)  # Built-in Python library for working with dates and times

# -----------------------------------------------------------------------------
# ADDED IMPORTS (for Cosmos DB persistence)
# -----------------------------------------------------------------------------
import os
import uuid
from azure.cosmos import CosmosClient

# =============================================================================
# CREATE THE FUNCTION APP
# =============================================================================
# This creates our Function App with anonymous access (no authentication required)
# Think of this as the "container" that holds all our functions
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# -----------------------------------------------------------------------------
# ADDED: Cosmos DB helper (connect to DB + return container)
# -----------------------------------------------------------------------------
def get_cosmos_container():
    endpoint = os.environ.get("COSMOS_ENDPOINT")
    key = os.environ.get("COSMOS_KEY")
    db_name = os.environ.get("COSMOS_DATABASE")
    container_name = os.environ.get("COSMOS_CONTAINER")

    if not endpoint or not key or not db_name or not container_name:
        raise ValueError(
            "Missing Cosmos settings. Required: COSMOS_ENDPOINT, COSMOS_KEY, COSMOS_DATABASE, COSMOS_CONTAINER"
        )

    client = CosmosClient(endpoint, credential=key)
    database = client.get_database_client(db_name)
    container = database.get_container_client(container_name)
    return container


# =============================================================================
# DEFINE THE TEXT ANALYZER FUNCTION
# =============================================================================
# The @app.route decorator tells Azure: "When someone visits /api/TextAnalyzer, run this function"
# This is called a "decorator" - it adds extra behavior to our function
@app.route(route="TextAnalyzer")
def TextAnalyzer(req: func.HttpRequest) -> func.HttpResponse:
    """
    This function analyzes text and returns statistics about it.

    Parameters:
        req: The incoming HTTP request (contains the text to analyze)

    Returns:
        func.HttpResponse: JSON response with analysis results
    """

    # Log a message so we can see in Azure Portal when the function is called
    logging.info("Text Analyzer API was called!")

    # =========================================================================
    # STEP 1: GET THE TEXT INPUT
    # =========================================================================
    # First, try to get 'text' from the URL query string
    # Example URL: /api/TextAnalyzer?text=Hello world
    # req.params.get('text') would return "Hello world"
    text = req.params.get("text")

    # If text wasn't in the URL, try to get it from the request body (JSON)
    if not text:
        try:
            # Try to parse the request body as JSON
            # Example body: {"text": "Hello world"}
            req_body = req.get_json()
            text = req_body.get("text")
        except ValueError:
            # If the body isn't valid JSON, just continue (text stays None)
            pass

    # =========================================================================
    # STEP 2: ANALYZE THE TEXT (if text was provided)
    # =========================================================================
    if text:
        # ----- Word Analysis -----
        # split() breaks the text into a list of words
        # "Hello world" becomes ["Hello", "world"]
        words = text.split()

        # len() counts items in a list
        # ["Hello", "world"] has length 2
        word_count = len(words)

        # ----- Character Analysis -----
        # len() on a string counts characters (including spaces)
        # "Hello world" has 11 characters
        char_count = len(text)

        # replace(" ", "") removes all spaces, then we count
        # "Hello world" becomes "Helloworld" (10 characters)
        char_count_no_spaces = len(text.replace(" ", ""))

        # ----- Sentence Analysis -----
        # re.findall() finds all matches of a pattern
        # r'[.!?]+' means: find any sequence of periods, exclamation marks, or question marks
        # "Hello! How are you?" returns ['!', '?'] (2 sentences)
        # The "or 1" means: if no punctuation found, assume at least 1 sentence
        sentence_count = len(re.findall(r"[.!?]+", text)) or 1

        # ----- Paragraph Analysis -----
        # Paragraphs are separated by blank lines (two newlines: \n\n)
        # split('\n\n') breaks text at blank lines
        # We filter out empty paragraphs with "if p.strip()"
        # strip() removes whitespace - empty strings become "" which is False
        paragraph_count = len([p for p in text.split("\n\n") if p.strip()])

        # ----- Reading Time Calculation -----
        # Average reading speed is about 200 words per minute
        # round(x, 1) rounds to 1 decimal place
        # 100 words / 200 wpm = 0.5 minutes
        reading_time_minutes = round(word_count / 200, 1)

        # ----- Average Word Length -----
        # Total characters (no spaces) divided by number of words
        # We check "if word_count > 0" to avoid dividing by zero
        avg_word_length = (
            round(char_count_no_spaces / word_count, 1) if word_count > 0 else 0
        )

        # ----- Find Longest Word -----
        # max() finds the largest item
        # key=len means "compare words by their length"
        # max(["Hi", "Hello", "Hey"], key=len) returns "Hello"
        longest_word = max(words, key=len) if words else ""

        # =====================================================================
        # STEP 3: BUILD THE RESPONSE
        # =====================================================================
        # Create a Python dictionary with all our analysis results
        # This will be converted to JSON format
        response_data = {
            "analysis": {
                "wordCount": word_count,
                "characterCount": char_count,
                "characterCountNoSpaces": char_count_no_spaces,
                "sentenceCount": sentence_count,
                "paragraphCount": paragraph_count,
                "averageWordLength": avg_word_length,
                "longestWord": longest_word,
                "readingTimeMinutes": reading_time_minutes,
            },
            "metadata": {
                # datetime.utcnow() gets current time, isoformat() converts to string
                # Example: "2024-01-15T14:30:00.000000"
                "analyzedAt": datetime.utcnow().isoformat(),
                # Show first 100 characters of text as a preview
                # The syntax: value_if_true if condition else value_if_false
                # This is called a "ternary operator" or "conditional expression"
                "textPreview": text[:100] + "..." if len(text) > 100 else text,
            },
        }

       
        # ADDED: Persist to Cosmos DB and ID

        record_id = str(uuid.uuid4())

        document = {
            "id": record_id,
            "analysesid": "analysis", # partition Key
            "analysis": response_data["analysis"],
            "metadata": response_data["metadata"],
            "originalText": text,
        }

        try:
            container = get_cosmos_container()
            container.upsert_item(document)
        except Exception as ex:
            logging.exception("Cosmos DB insert failed.")
            return func.HttpResponse(
                json.dumps(
                    {"error": "Database insert failed", "details": str(ex)}, indent=2
                ),
                mimetype="application/json",
                status_code=500,
            )

        # Add the stored record id 
        response_data["id"] = record_id

        return func.HttpResponse(
            json.dumps(response_data, indent=2),
            mimetype="application/json",
            status_code=200,
        )

    # =========================================================================
    # STEP 4: HANDLE MISSING TEXT (Error Response)
    # =========================================================================
    else:
        # If no text was provided, return helpful instructions
        instructions = {
            "error": "No text provided",
            "howToUse": {
                "option1": "Add ?text=YourText to the URL",
                "option2": 'Send a POST request with JSON body: {"text": "Your text here"}',
                "example": "https://your-function-url/api/TextAnalyzer?text=Hello world",
            },
        }

        # Return an error response
        # status_code=400 means "Bad Request - client made an error"
        return func.HttpResponse(
            json.dumps(instructions, indent=2),
            mimetype="application/json",
            status_code=400,
        )


# ADDED: GetAnalysisHistory endpoint
# Route: /api/GetAnalysisHistory

@app.route(route="GetAnalysisHistory", methods=["GET"])
def GetAnalysisHistory(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("GetAnalysisHistory API was called!")

    limit_raw = req.params.get("limit")
    try:
        limit = int(limit_raw) if limit_raw else 10
        if limit <= 0:
            limit = 10
        if limit > 50:
            limit = 50
    except ValueError:
        limit = 10

    try:
        container = get_cosmos_container()

        query = """
        SELECT TOP @limit c.id, c.analysis, c.metadata
        FROM c
        WHERE c.analysesid = "analysis"
        ORDER BY c.metadata.analyzedAt DESC
        """
        params = [{"name": "@limit", "value": limit}]

        items = list(
            container.query_items(
                query=query, parameters=params, enable_cross_partition_query=True
            )
        )

    except Exception as ex:
        logging.exception("Cosmos DB query failed.")
        return func.HttpResponse(
            json.dumps(
                {"error": "Database query failed", "details": str(ex)}, indent=2
            ),
            mimetype="application/json",
            status_code=500,
        )

    result = {"count": len(items), "results": items}

    return func.HttpResponse(
        json.dumps(result, indent=2), mimetype="application/json", status_code=200
    )
