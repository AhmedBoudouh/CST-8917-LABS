# Database Choice for Text Analyzer

## Selected Database
**Azure Cosmos DB** (with NoSQL API in serverless mode)

## Justification
Cosmos DB is ideal for this use case because it natively stores JSON documents without requiring schema definition, which perfectly matches our analysis output format. The serverless tier provides automatic scaling and pay-per-request pricing, aligning with our Azure Function's serverless architecture. The free tier offers 1000 RU/s and 25GB storage, which is more than sufficient for a student project storing text analysis results.

## Alternatives Considered

| Database | Why Rejected |
|----------|--------------|
| **Azure Table Storage** | Requires flattening JSON into key-value pairs; less intuitive querying for complex nested data |
| **Azure SQL Database** | Requires schema definition; JSON support exists but adds complexity; higher baseline costs |
| **Azure Blob Storage** | Not a true database; no querying capabilities without additional indexing; requires manual file management |

## Cost Considerations

### Free Tier
- **1000 RU/s throughput** (sufficient for thousands of requests)
- **25 GB storage** (ample for text analysis results)
- No time limit (always free)

### Serverless Pricing (beyond free tier)
- **Request Units**: $0.25 per million RUs consumed
- **Storage**: $0.25 per GB/month
- **No minimum charges** - only pay for actual usage
- Ideal for intermittent workloads like student projects

## Technical Benefits
- **Native JSON support** - store analysis results directly
- **Automatic indexing** - query results without manual index creation
- **Python SDK** - excellent integration with Azure Functions (`azure-cosmos` package)
- **No schema required** - flexible for evolving analysis features
- **Global distribution** - optional scalability for future needs
