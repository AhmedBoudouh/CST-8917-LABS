# Lab 4 — PhotoPipe: Event-Driven Image Processing

**Course:** CST8917 — Serverless Computing  
**Student:** Ahmed Boudouh

---

## Demo Video

https://youtu.be/S3tM4BAwCt8

---

## Project Overview

PhotoPipe is a serverless image processing pipeline on Azure. When a user uploads an image through the web client, the system automatically processes it and keeps an audit log — with no manual steps needed.

---

## Architecture

```
User uploads image
       ↓
Blob Storage (image-uploads)
       ↓
Event Grid System Topic (photopipe-blob-events)
       ↓                          ↓
process-image function       audit-log function
(only .jpg / .png)           (all uploads)
       ↓                          ↓
image-results container      Table Storage (auditlogs)
```

---

## Azure Resources Created

| Resource | Name |
|---|---|
| Resource Group | rg-serverless-lab4 |
| Storage Account | ahmedphotopipe |
| Blob Container (uploads) | image-uploads |
| Blob Container (results) | image-results |
| Table Storage | auditlogs |
| Function App | ahmed-photopipe-func |
| Event Grid System Topic | photopipe-blob-events |
| Event Subscription 1 | process-image-sub (filters .jpg / .png) |
| Event Subscription 2 | audit-log-sub (all blob events) |

---

## Functions Deployed

| Function | Trigger | What it does |
|---|---|---|
| `process-image` | Event Grid | Reads uploaded image, writes metadata JSON to image-results |
| `audit-log` | Event Grid | Logs every upload event to Table Storage |
| `get-results` | HTTP GET | Returns all processed image metadata |
| `get-audit-log` | HTTP GET | Returns all audit log entries |
| `health` | HTTP GET | Checks that the service is running |

---

## Setup Steps (What I Did)

**Part 1 — Storage Account**
- Created storage account `ahmedphotopipe`
- Enabled anonymous blob access
- Created `image-uploads` (public) and `image-results` containers
- Configured CORS to allow all origins

**Part 2 — Azure Functions**
- Created Python 3.11 Function App `ahmed-photopipe-func`
- Wrote and deployed all 5 functions
- Added `STORAGE_CONNECTION_STRING` to application settings
- Configured CORS on the Function App

**Part 3 — Event Grid**
- Created System Topic `photopipe-blob-events` linked to the storage account
- Created `process-image-sub` with subject filter for `.jpg` and `.png` files
- Created `audit-log-sub` to capture all blob creation events

**Part 4 — Web Client**
- Deployed the web client with storage account name, function URL, and SAS token
- Tested by uploading images and a non-image file
- Confirmed: images trigger both functions, non-images trigger only audit-log

---

## Testing Results

- Uploaded `panda.png` → metadata JSON created in `image-results` 
- Uploaded `plan.txt` → audit entry created, no image processing 
- Event Grid metrics confirmed: 3 events published, matched, and delivered 
- Web client showed: 2 uploaded, 1 processed, 2 audit entries 
