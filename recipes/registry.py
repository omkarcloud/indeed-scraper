"""Which machine runs a site's browser work in the hosted service. This repo has
none: every site maps to a machine no address is configured for, so
browser_client answers BoxUnavailable ("no browser right now") and the site
reports the page as blocked instead of solving it in a browser."""


def box_for(site):
    return "none"
