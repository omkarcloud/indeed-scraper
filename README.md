![Indeed Scraper Featured Image](https://raw.githubusercontent.com/omkarcloud/indeed-scraper/master/indeed-scraper-featured-image.png)

# Indeed Scraper API

Search Indeed job listings and get full posting details — title, salary, company, qualifications, benefits — as structured JSON via a simple REST API. 5,000 free requests/month.

## Key Features

- Search jobs by keyword with optional location filtering
- Get full job details: salary range, benefits, qualifications, description HTML
- Company metadata including ratings and review counts
- Pagination support for large result sets
- **5,000 requests/month on free tier**
- Example Response:
```json
{
  "job_id": "a8f3e9c2d4b617fa",
  "title": "Senior Software Engineer, Cloud Infrastructure",
  "company": "Apple",
  "company_rating": 4.3,
  "location": "Cupertino, CA 95014",
  "remote_work_model": "hybrid",
  "salary_snippet": "$175,000 - $250,000 a year",
  "job_type": "Full-time",
  "posted_at": "3 days ago"
}
```

## Get API Key

Create an account at [omkar.cloud](https://www.omkar.cloud/auth/sign-up?redirect=/api-key) to get your API key.

It takes just 2 minutes to sign up. You get 5,000 free requests every month for detailed Indeed data — more than enough for most users to get their job done without paying a dime.

This is a well built product, and your search for the best Indeed Scraper API ends right here.


## Quick Start

```bash
curl -X GET "https://indeed-scraper.omkar.cloud/indeed/search?search_term=software%20engineer&location=New%20York" \
  -H "API-Key: YOUR_API_KEY"
```

```json
{
  "total_results": 4283,
  "jobs": [
    {
      "job_id": "a8f3e9c2d4b617fa",
      "title": "Senior Software Engineer, Cloud Infrastructure",
      "company": "Apple",
      "company_rating": 4.3,
      "location": "Cupertino, CA 95014",
      "remote_work_model": "hybrid",
      "salary_snippet": "$175,000 - $250,000 a year",
      "job_type": "Full-time",
      "posted_at": "3 days ago"
    }
  ]
}
```

## Quick Start (Python)

```bash
pip install requests
```

```python
import requests

response = requests.get(
    "https://indeed-scraper.omkar.cloud/indeed/search",
    params={"search_term": "software engineer", "location": "New York"},
    headers={"API-Key": "YOUR_API_KEY"}
)

print(response.json())
```


## API Reference

### Search Jobs

```
GET https://indeed-scraper.omkar.cloud/indeed/search
```

#### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `search_term` | Yes | — | Job title, skill, or company keyword used to find matching listings. |
| `location` | No | — | City, state, or region to narrow the job search. |
| `page` | No | `1` | Page number for paginated results. |

#### Example

```python
import requests

response = requests.get(
    "https://indeed-scraper.omkar.cloud/indeed/search",
    params={"search_term": "software engineer", "location": "New York"},
    headers={"API-Key": "YOUR_API_KEY"}
)

print(response.json())
```

#### Response

<details>
<summary>Sample Response (click to expand)</summary>

```json
{
    "total_results": 4283,
    "jobs": [
      {
        "job_id": "a8f3e9c2d4b617fa",
        "title": "Senior Software Engineer, Cloud Infrastructure",
        "company": "Apple",
        "company_rating": 4.3,
        "company_reviews_count": 24817,
        "location": "Cupertino, CA 95014",
        "remote_work_model": "hybrid",
        "salary_snippet": "$175,000 - $250,000 a year",
        "job_type": "Full-time",
        "posted_at": "3 days ago",
        "description_snippet": "Build and scale the cloud infrastructure behind iCloud, Apple Music, and Apple TV+. Work with distributed systems at massive scale serving hundreds of millions of users...",
        "job_url": "https://www.indeed.com/viewjob?jk=a8f3e9c2d4b617fa",
        "is_sponsored": false
      },
      {
        "job_id": "7b21d0e5f8ca49a3",
        "title": "Machine Learning Engineer, Siri",
        "company": "Apple",
        "company_rating": 4.3,
        "company_reviews_count": 24817,
        "location": "Seattle, WA 98109",
        "remote_work_model": "on-site",
        "salary_snippet": "$190,000 - $280,000 a year",
        "job_type": "Full-time",
        "posted_at": "Just posted",
        "description_snippet": "Join the Siri team to develop and deploy on-device ML models for natural language understanding. Deep experience with PyTorch, transformer architectures, and on-device optimization required...",
        "job_url": "https://www.indeed.com/viewjob?jk=7b21d0e5f8ca49a3",
        "is_sponsored": false
      },
      {
        "job_id": "e4c6a1b9d3f285e7",
        "title": "iOS Software Engineer",
        "company": "Apple",
        "company_rating": 4.3,
        "company_reviews_count": 24817,
        "location": "Austin, TX 78727",
        "remote_work_model": "on-site",
        "salary_snippet": "$140,000 - $210,000 a year",
        "job_type": "Full-time",
        "posted_at": "1 week ago",
        "description_snippet": "Work on core iOS frameworks used by millions of developers worldwide. You will design and implement APIs in Swift and Objective-C that ship on every iPhone, iPad, and Mac...",
        "job_url": "https://www.indeed.com/viewjob?jk=e4c6a1b9d3f285e7",
        "is_sponsored": true
      }
    ]
}
```

</details>

---

### Job Details

```
GET https://indeed-scraper.omkar.cloud/indeed/job
```

#### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `job_id` | Yes | — | Unique Indeed job posting identifier (the `jk` value from a listing URL). |

#### Example

```python
import requests

response = requests.get(
    "https://indeed-scraper.omkar.cloud/indeed/job",
    params={"job_id": "a8f3e9c2d4b617fa"},
    headers={"API-Key": "YOUR_API_KEY"}
)

print(response.json())
```

#### Response Fields

Returns full job posting data including title, structured salary (min/max/currency/period), description HTML, benefits list, qualifications, company metadata with logo, and apply URL.

<details>
<summary>Sample Response (click to expand)</summary>

```json
{
    "job_id": "a8f3e9c2d4b617fa",
    "title": "Senior Software Engineer, Cloud Infrastructure",
    "company": "Apple",
    "company_rating": 4.3,
    "company_reviews_count": 24817,
    "company_logo_url": "https://d2q79iu7y748jz.cloudfront.net/s/_squarelogo/128x128/apple_logo.png",
    "location": "Cupertino, CA 95014",
    "remote_work_model": "hybrid",
    "salary": {
      "min": 175000,
      "max": 250000,
      "currency": "USD",
      "period": "yearly"
    },
    "job_type": "Full-time",
    "posted_at": "3 days ago",
    "description_html": "<p><b>About the role</b></p><p>Apple's Cloud Services team is looking for a Senior Software Engineer to build and scale the infrastructure behind iCloud, Apple Music, and Apple TV+. You will work on distributed systems serving hundreds of millions of users worldwide.</p><ul><li>Design and implement highly available services processing millions of requests per second</li><li>Collaborate with security and privacy teams to uphold Apple's commitment to user data protection</li></ul><p><b>Qualifications</b></p><ul><li>7+ years of professional software engineering experience</li><li>Strong proficiency in Java, Go, or Scala</li><li>Deep experience with distributed systems, Kubernetes, and large-scale data pipelines</li><li>Track record of designing systems that operate at Apple-level scale</li></ul>",
    "benefits": [
      "Health and dental insurance",
      "401(k) matching",
      "Employee stock purchase plan",
      "Flexible work schedule",
      "Product discounts",
      "Wellness reimbursement"
    ],
    "qualifications": [
      "7+ years of professional software engineering experience",
      "Strong proficiency in Java, Go, or Scala",
      "Deep experience with distributed systems and Kubernetes"
    ],
    "job_url": "https://www.indeed.com/viewjob?jk=a8f3e9c2d4b617fa",
    "apply_url": "https://www.indeed.com/applystart?jk=a8f3e9c2d4b617fa",
    "is_sponsored": false
}
```

</details>

## Error Handling

```python
response = requests.get(
    "https://indeed-scraper.omkar.cloud/indeed/search",
    params={"search_term": "data engineer"},
    headers={"API-Key": "YOUR_API_KEY"}
)

if response.status_code == 200:
    data = response.json()
elif response.status_code == 401:
    # Invalid API key
    pass
elif response.status_code == 429:
    # Rate limit exceeded
    pass
```

## FAQs

### What data does the Search Jobs endpoint return?

Per job listing:
- Job ID, title, company name, and company rating
- Location and remote work model (remote, hybrid, on-site)
- Salary snippet and job type (full-time, part-time, contract)
- Posting age, description snippet, and direct job URL
- Sponsored flag

All in structured JSON. Ready to use in your app.

### What extra data does Job Details return over Search?

Job Details gives you everything Search returns, plus:
- Full description as HTML
- Structured salary breakdown (min, max, currency, period)
- Benefits list and qualifications list
- Company logo URL and review count
- Direct apply URL

### Can I filter jobs by location?

Yes. Pass the `location` parameter with any city, state, or region (e.g., `New York, NY`, `Remote`, `San Francisco`). If omitted, results are returned for all locations.

### How accurate is the data?

Data is pulled from Indeed in real time. Every API call fetches live listings — not cached or stale results. Job titles, salaries, and posting dates reflect what's on Indeed right now.

## Rate Limits

| Plan | Price | Requests/Month |
|------|-------|----------------|
| Free | $0 | 5,000 |
| Starter | $25 | 100,000 |
| Grow | $75 | 1,000,000 |
| Scale | $150 | 10,000,000 |

## Questions? We have answers.

Reach out anytime. We will solve your query within 1 working day.

[![Contact Us on WhatsApp about Indeed Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20have%20a%20question%20about%20the%20Indeed%20Scraper%20API.)

[![Contact Us on Email about Indeed Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Indeed%20Scraper%20API%20Question)
