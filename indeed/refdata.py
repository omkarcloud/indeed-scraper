"""Static Indeed reference tables, captured from the live site 2026-09-26.

  COUNTRIES          the 62 countries the GraphQL API accepts in `indeed-co`
                     (every other ISO code answers "does not correspond to a
                     valid Indeed site"), with their web host
  JOB_TYPES ...      job attribute ids ("suids") the site's own search filters
                     use, grouped the way the web job cards group them; used to
                     build search filters and to split a job's flat attribute
                     list into readable groups
  REVIEW_TOPICS      the five review topics (ftopic=)
  QUESTION_TOPICS    Q&A topic ids -> the /cmp/<slug>/faq/<seo-url> segment
  SALARY_CATEGORIES  company-salary job categories (job_category=)
"""

# ISO code -> (English name, web host). The API also accepts AQ (a placeholder
# "worldwide" site with no pages), which is left out.
COUNTRIES = {
    "AE": ("United Arab Emirates", "ae.indeed.com"), "AR": ("Argentina", "ar.indeed.com"),
    "AT": ("Austria", "at.indeed.com"), "AU": ("Australia", "au.indeed.com"),
    "BE": ("Belgium", "be.indeed.com"), "BH": ("Bahrain", "bh.indeed.com"),
    "BR": ("Brazil", "br.indeed.com"), "CA": ("Canada", "ca.indeed.com"),
    "CH": ("Switzerland", "ch.indeed.com"), "CL": ("Chile", "cl.indeed.com"),
    "CN": ("China", "cn.indeed.com"), "CO": ("Colombia", "co.indeed.com"),
    "CR": ("Costa Rica", "cr.indeed.com"), "CZ": ("Czech Republic", "cz.indeed.com"),
    "DE": ("Germany", "de.indeed.com"), "DK": ("Denmark", "dk.indeed.com"),
    "EC": ("Ecuador", "ec.indeed.com"), "EG": ("Egypt", "eg.indeed.com"),
    "ES": ("Spain", "es.indeed.com"), "FI": ("Finland", "fi.indeed.com"),
    "FR": ("France", "fr.indeed.com"), "GB": ("United Kingdom", "uk.indeed.com"),
    "GR": ("Greece", "gr.indeed.com"), "HK": ("Hong Kong", "hk.indeed.com"),
    "HU": ("Hungary", "hu.indeed.com"), "ID": ("Indonesia", "id.indeed.com"),
    "IE": ("Ireland", "ie.indeed.com"), "IL": ("Israel", "il.indeed.com"),
    "IN": ("India", "in.indeed.com"), "IT": ("Italy", "it.indeed.com"),
    "JP": ("Japan", "jp.indeed.com"), "KR": ("South Korea", "kr.indeed.com"),
    "KW": ("Kuwait", "kw.indeed.com"), "LU": ("Luxembourg", "lu.indeed.com"),
    "MA": ("Morocco", "ma.indeed.com"), "MX": ("Mexico", "mx.indeed.com"),
    "MY": ("Malaysia", "my.indeed.com"), "NG": ("Nigeria", "ng.indeed.com"),
    "NL": ("Netherlands", "nl.indeed.com"), "NO": ("Norway", "no.indeed.com"),
    "NZ": ("New Zealand", "nz.indeed.com"), "OM": ("Oman", "om.indeed.com"),
    "PA": ("Panama", "pa.indeed.com"), "PE": ("Peru", "pe.indeed.com"),
    "PH": ("Philippines", "ph.indeed.com"), "PK": ("Pakistan", "pk.indeed.com"),
    "PL": ("Poland", "pl.indeed.com"), "PT": ("Portugal", "pt.indeed.com"),
    "QA": ("Qatar", "qa.indeed.com"), "RO": ("Romania", "ro.indeed.com"),
    "SA": ("Saudi Arabia", "sa.indeed.com"), "SE": ("Sweden", "se.indeed.com"),
    "SG": ("Singapore", "sg.indeed.com"), "TH": ("Thailand", "th.indeed.com"),
    "TR": ("Turkey", "tr.indeed.com"), "TW": ("Taiwan", "tw.indeed.com"),
    "UA": ("Ukraine", "ua.indeed.com"), "US": ("United States", "www.indeed.com"),
    "UY": ("Uruguay", "uy.indeed.com"), "VE": ("Venezuela", "ve.indeed.com"),
    "VN": ("Vietnam", "vn.indeed.com"), "ZA": ("South Africa", "za.indeed.com"),
}
# Local currency per country (salary pages print amounts in it, symbol only).
CURRENCIES = {
    "AE": "AED", "AR": "ARS", "AT": "EUR", "AU": "AUD", "BE": "EUR", "BH": "BHD", "BR": "BRL", "CA": "CAD",
    "CH": "CHF", "CL": "CLP", "CN": "CNY", "CO": "COP", "CR": "CRC", "CZ": "CZK", "DE": "EUR", "DK": "DKK",
    "EC": "USD", "EG": "EGP", "ES": "EUR", "FI": "EUR", "FR": "EUR", "GB": "GBP", "GR": "EUR", "HK": "HKD",
    "HU": "HUF", "ID": "IDR", "IE": "EUR", "IL": "ILS", "IN": "INR", "IT": "EUR", "JP": "JPY", "KR": "KRW",
    "KW": "KWD", "LU": "EUR", "MA": "MAD", "MX": "MXN", "MY": "MYR", "NG": "NGN", "NL": "EUR", "NO": "NOK",
    "NZ": "NZD", "OM": "OMR", "PA": "USD", "PE": "PEN", "PH": "PHP", "PK": "PKR", "PL": "PLN", "PT": "EUR",
    "QA": "QAR", "RO": "RON", "SA": "SAR", "SE": "SEK", "SG": "SGD", "TH": "THB", "TR": "TRY", "TW": "TWD",
    "UA": "UAH", "US": "USD", "UY": "UYU", "VE": "VES", "VN": "VND", "ZA": "ZAR",
}
# host label -> ISO code, for links on any Indeed host ("uk" -> GB, "www" -> US)
HOST_COUNTRIES = {host.split(".")[0]: code for code, (_, host) in COUNTRIES.items()}
HOST_COUNTRIES.update({"indeed": "US", "m": "US"})
# countries whose distances are shown in miles on Indeed
MILES_COUNTRIES = {"US", "GB"}

# ---- job attributes ----------------------------------------------------------------
# Public filter value -> attribute id, and id -> readable label.
JOB_TYPES = {
    "full_time": ("CF3CP", "Full-time"), "part_time": ("75GKK", "Part-time"),
    "contract": ("NJXCK", "Contract"), "temporary": ("4HKF7", "Temporary"),
    "permanent": ("5QWDV", "Permanent"), "internship": ("VDTG7", "Internship"),
    "temp_to_hire": ("7SBAT", "Temp-to-hire"), "seasonal": ("9SYVT", "Seasonal"),
    "freelance": ("ZG59D", "Freelance"), "apprenticeship": ("CPAHG", "Apprenticeship"),
    "volunteer": ("UXQZ8", "Volunteer"),
}
WORK_SETTINGS = {"remote": ("DSQF7", "Remote"), "hybrid": ("PAXZC", "Hybrid work")}
EXPERIENCE_LEVELS = {
    "no_experience": ("D7S5D", "No experience needed"), "entry_level": ("Y4JG9", "Entry level"),
    "mid_level": ("DN563", "Mid-level"), "senior_level": ("UB7SC", "Senior level"),
}
EDUCATION_LEVELS = {
    "high_school": ("FCGTU", "High school diploma or GED"), "associate": ("UTPWG", "Associate's degree"),
    "bachelor": ("HFDVW", "Bachelor's degree"), "master": ("EXSNN", "Master's degree"),
    "doctorate": ("6QC5F", "Doctoral degree"),
}
# id -> label for the groups a job's attributes are split into
JOB_TYPE_IDS = {v[0]: v[1] for v in JOB_TYPES.values()}
WORK_SETTING_IDS = {"DSQF7": "remote", "PAXZC": "hybrid"}
EXPERIENCE_LEVEL_IDS = {v[0]: k for k, v in EXPERIENCE_LEVELS.items()}
SCHEDULE_IDS = {
    "PMS5Q": "Day shift", "KPAXE": "On demand", "SAP7A": "Monday to Friday", "5WFZM": "Overtime",
    "VZD9Q": "On call", "H3N5U": "Night shift", "9TG7M": "Overnight shift", "7SRRR": "Weekends as needed",
    "VDB9U": "Holidays", "RAXWH": "Home time",
}
BENEFIT_IDS = {
    "AWHEP": "Paid holidays", "FQJ2X": "Dental insurance", "EY33Q": "Health insurance",
    "CFRGS": "Disability insurance", "SENX8": "401(k) matching", "HW4J4": "Paid time off",
    "RZAT2": "Vision insurance", "NPHPU": "Parental leave", "Y2WS5": "Life insurance",
    "72VVG": "Paid parental leave", "YQ98H": "Retirement plan", "V2CTH": "Loan forgiveness",
    "FVKX2": "401(k)", "QXB7R": "Employee assistance program", "WZ9TD": "Flexible schedule",
    "9TE9M": "AD&D insurance", "K5S2U": "Adoption assistance", "G85UP": "Flexible spending account",
    "HCRPT": "RSU", "3K96F": "Free parking", "N83EH": "Work from home", "6XT6J": "Stock options",
    "7KV6C": "Health savings account", "JXM7M": "Cell phone reimbursement", "YJ8XR": "Food provided",
    "HJUWZ": "Tuition reimbursement", "NA9HP": "Bonus opportunities", "BR3R3": "Yearly bonus",
    "AV9NF": "Employee stock purchase plan", "79D7W": "Performance bonus", "ZA2SS": "Signing bonus",
    "8NCA8": "Overtime pay", "4C2ZW": "Profit sharing", "VQ9BR": "Semiannual bonus",
    "BW7JZ": "Quarterly bonus", "USD42": "Employee stock ownership plan", "4WUF7": "Retention bonus",
}
PAY_TYPE_IDS = {"8AD9K": "Hourly pay", "3A8KY": "Commission pay", "V7KSJ": "1099 contract"}

# ---- company pages -------------------------------------------------------------------
REVIEW_TOPICS = {
    "work_life_balance": "wlbalance", "pay_and_benefits": "paybenefits",
    "job_security_and_advancement": "jobsecadv", "management": "mgmt", "culture": "culture",
}
REVIEW_SORTS = {"newest": None, "oldest": "date_asc", "highest_rating": "rating_desc",
                "lowest_rating": "rating_asc"}

QUESTION_TOPICS = {
    "hiring_process": "hiring-process", "work_from_home": "work-from-home", "interviews": "interviews",
    "benefits": "benefits", "working_hours": "working-hours", "job_opportunities": "job-opportunities",
    "salary": "salary", "hiring_age": "hiring-age", "dress_code": "dress-code", "drug_test": "drug-test",
    "promotion": "promotion", "working_environment": "working-environment",
    "office_locations": "office-locations", "attire": "attire", "background_check": "background-check",
    "part_time": "part-time", "working_culture": "working-culture", "training": "training", "ceo": "ceo",
    "health_benefits": "health-benefits", "company_future": "company-future",
    "dental_benefits": "dental-benefits", "firing": "firing", "life_insurance": "life-insurance",
    "401k": "401k", "union": "union", "work_life_balance": "work-life-balance",
}

SALARY_CATEGORIES = {
    "accounting": "Accounting", "admin": "Administrative Assistance", "agriculture": "Agriculture & Forestry",
    "arch": "Architecture", "arts": "Arts & Entertainment", "aviation": "Aviation",
    "finance": "Banking & Finance", "personal": "Beauty & Wellness", "bizops": "Business Operations",
    "callcenter": "Call Center", "engchem": "Chemical Engineering", "childcare": "Childcare",
    "engcivil": "Civil Engineering", "sanitation": "Cleaning & Sanitation",
    "service": "Community & Social Service", "construction": "Construction", "customer": "Customer Service",
    "driver": "Driving", "education": "Education & Instruction", "engelectric": "Electrical Engineering",
    "food": "Food Preparation & Service", "hospitality": "Hospitality & Tourism", "hr": "Human Resources",
    "techhelp": "IT Operations & Helpdesk", "engid": "Industrial Engineering",
    "techinfo": "Information Design & Documentation", "install": "Installation & Maintenance",
    "insurance": "Insurance", "legal": "Legal", "warehouse": "Loading and Stocking",
    "transport": "Logistic Support", "management": "Management", "marketing": "Marketing",
    "math": "Mathematics", "engmech": "Mechanical Engineering", "media": "Media & Communications",
    "medinfo": "Medical Information", "medtech": "Medical Technician", "military": "Military",
    "mednurse": "Nursing", "pharmacy": "Pharmacy", "meddr": "Physicians & Surgeons",
    "manufacturing": "Production & Manufacturing", "project": "Project Management",
    "realestate": "Real Estate", "retail": "Retail", "sales": "Sales",
    "science": "Scientific Research & Development", "protective": "Security & Public Safety",
    "socialscience": "Social Science", "techsoftware": "Software Development", "sports": "Sports",
    "therapy": "Therapy", "uncategorized": "Uncategorized",
}
