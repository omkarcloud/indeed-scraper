"""Marshmallow request schemas for every /indeed/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Indeed resolvers (refs.py). Every schema's load() output is the
kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes a job key OR any indeed.com job link;
`company` a page name, a company name, an indeed.com/cmp/ link or an
employer id; `job_title` a title or a /career/ link; `country` an ISO code,
an English name or an indeed.com link on that country's site.
"""
import re

from marshmallow import ValidationError, fields, validate

from indeed import refdata, refs
from indeed.search import AUTOCOMPLETE_TYPES
from schema_fields import (BaseSchema, ChoiceField, CommaListField, LanguageCodeField, PageField, PositiveInt,
                           QueryField, RefField, StrippedString, COUNTRY_CODES)

MAX_BATCH = 20
_ATTRIBUTE_ID_RE = re.compile(r"^[0-9A-Z]{5}$")


class CountryField(RefField):
    """The Indeed site: ISO code / English name / indeed.com link. Default US."""
    resolver = staticmethod(refs.resolve_country)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", "US")
        super().__init__(**kwargs)


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class OptionalCompanyField(CompanyField):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobTitleField(RefField):
    resolver = staticmethod(refs.resolve_job_title)


class CareerLocationField(RefField):
    resolver = staticmethod(refs.career_location_segment)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobListField(fields.Field):
    """'bca244a4074f26cb, https://www.indeed.com/viewjob?jk=…' -> ['bca2…', …]
    (resolved, deduped, 1..MAX_BATCH)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        out = []
        for item in str(value or "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                key = refs.resolve_job(item)
            except ValueError as e:
                raise ValidationError(f"'{item}': {e}")
            if key not in out:
                out.append(key)
        if not out:
            raise ValidationError("Must list at least one job key or link (comma-separated).")
        if len(out) > MAX_BATCH:
            raise ValidationError(f"At most {MAX_BATCH} jobs.")
        return out


class AttributeIdsField(CommaListField):
    """Indeed attribute / occupation ids from /indeed/jobs/filters ('X62BT,CF3CP')."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_items", 10)
        super().__init__(upper=True, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        for item in items or []:
            if not _ATTRIBUTE_ID_RE.match(item):
                raise ValidationError(f"'{item}' is not an Indeed id (5 letters/digits, from /indeed/jobs/filters).")
        return items


class ReviewCountryField(StrippedString):
    """Reviewers' country: an ISO code, or 'all' (the default) for every country."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None or value.lower() in ("all", "any", "*"):
            return None
        code = value.upper()
        if code == "UK":
            code = "GB"
        if code not in COUNTRY_CODES:
            raise ValidationError("Must be a 2-letter ISO country code (US, IN, GB, ...) or 'all'.")
        return code


def _choices_with_names(table):
    """{id: name} -> a ChoiceField map accepting the id OR the name."""
    mapping = {key: key for key in table}
    mapping.update({name: key for key, name in table.items()})
    return mapping


# ---- jobs ----------------------------------------------------------------------------------------

class _JobFilters(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=validate.Length(max=200))
    location = StrippedString(required=False, load_default=None, validate=validate.Length(max=150))
    country = CountryField()
    radius = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=0, max=200))
    radius_unit = ChoiceField(["miles", "km"])
    date_posted = ChoiceField(["last_24_hours", "last_3_days", "last_7_days", "last_14_days", "last_30_days"])
    job_type = ChoiceField(list(refdata.JOB_TYPES))
    work_setting = ChoiceField(list(refdata.WORK_SETTINGS))
    experience_level = ChoiceField(list(refdata.EXPERIENCE_LEVELS))
    education = ChoiceField(list(refdata.EDUCATION_LEVELS))
    min_salary = PositiveInt(max_value=10_000_000)


class JobSearchSchema(_JobFilters):
    sort = ChoiceField(["relevance", "date"], load_default="relevance")
    company = OptionalCompanyField()
    attributes = AttributeIdsField()
    occupations = AttributeIdsField(max_items=5)
    page = PageField(max_page=50)


class JobFiltersSchema(_JobFilters):
    company = OptionalCompanyField()
    attributes = AttributeIdsField()
    occupations = AttributeIdsField(max_items=5)


class JobSchema(BaseSchema):
    job = JobField()


class JobBatchSchema(BaseSchema):
    jobs = JobListField()


# ---- companies -------------------------------------------------------------------------------------

class CompanySearchSchema(BaseSchema):
    query = QueryField(max_length=100)
    location = StrippedString(required=False, load_default=None, validate=validate.Length(max=150))
    country = CountryField()


class CompanySchema(BaseSchema):
    company = CompanyField()
    country = CountryField()


class CompanyReviewsSchema(CompanySchema):
    page = PageField(max_page=1000)
    sort = ChoiceField(list(refdata.REVIEW_SORTS), load_default="newest")
    review_country = ReviewCountryField()
    location = StrippedString(required=False, load_default=None, validate=validate.Length(max=150))
    job_title = StrippedString(required=False, load_default=None, validate=validate.Length(max=150))
    topic = ChoiceField(list(refdata.REVIEW_TOPICS))
    language = LanguageCodeField(allow_locale=False)


class CompanySalariesSchema(CompanySchema):
    job_title = StrippedString(required=False, load_default=None, validate=validate.Length(min=2, max=150))
    location = StrippedString(required=False, load_default=None, validate=validate.Length(max=150))
    job_category = ChoiceField(_choices_with_names(refdata.SALARY_CATEGORIES))


class CompanyQuestionsSchema(CompanySchema):
    page = PageField(max_page=200)
    topic = ChoiceField(list(refdata.QUESTION_TOPICS))


class CompanyJobsSchema(_JobFilters):
    company = CompanyField()
    sort = ChoiceField(["relevance", "date"], load_default="relevance")
    page = PageField(max_page=50)


# ---- salaries / autocomplete ------------------------------------------------------------------------

class CareerSalariesSchema(BaseSchema):
    job_title = JobTitleField()
    location = CareerLocationField()
    country = CountryField()


class AutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100)
    type = ChoiceField(list(AUTOCOMPLETE_TYPES), load_default="job_titles")
    country = CountryField()
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=20))


class EmptySchema(BaseSchema):
    pass
