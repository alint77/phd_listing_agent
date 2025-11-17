# AI PhD Scraper Agent --- Project Summary & Plan

## Summary of the Design Conversation

You want to build an AI agent in Python that: - Scrapes **PhD
opportunities from FindAPhD.com** (initial target) - Collects **project
page URLs** from search results - Extracts **clean text blobs** from
project pages - Uses an **LLM** to extract structured fields: - title -
university - supervisor - funding (international eligible?) - alignment
with your interests - any other relevant attributes - Saves everything
to a **CSV** for review.

Your agent will also: - Use the **LLM to generate search queries**
themselves. - Use **batch inference** for efficiency (but NOT chunking
multiple blobs in one prompt). - Use a **polite scraper** (delays,
User-Agent header). - Avoid bypassing CAPTCHAs, relying instead on good
scraping hygiene.

## Final MVP Pipeline

### 1. User prompt → LLM (query generator)

LLM receives a high-level instruction such as: \> "Find PhDs in AI/ML
with funding for international students."

LLM outputs: - A list of FindAPhD search query URLs\
Example: - https://www.findaphd.com/phds/?Keywords=machine+learning\
- https://www.findaphd.com/phds/?Keywords=artificial+intelligence

### 2. Search query → Scraper (link collector)

For each query URL: - Fetch results page - Extract all `<a>` links
pointing to `/phds/...` - Produce a list of project URLs

### 3. Project URL → Scraper (clean text extractor)

For each project link: - Fetch HTML politely - Strip noise: `<script>`,
`<style>`, `<nav>`, `<footer>`, `<header>` - Extract visible text from:
`<p>`, `<h1-4>`, `<li>` - Produce one **clean text blob**

### 4. Text blob → LLM (structured data extraction)

LLM receives a clean blob + extraction prompt.

LLM outputs JSON fields:

    {
      "title": "...",
      "university": "...",
      "supervisor": "...",
      "funding": "...",
      "alignment": "...",
      "other": "..."
    }

### 5. CSV writer

-   Accumulate extracted JSON objects
-   Save them to `phd_listings.csv`

------------------------------------------------------------------------

## Core Functions (in MVP scaffold)

-   `generate_search_queries(user_prompt, llm)`
-   `get_project_links(search_url)`
-   `get_clean_text(project_url)`
-   `extract_project_info(text_blob, llm)`
-   `main_agent(user_prompt, llm)`

------------------------------------------------------------------------

## Notes & Next Steps

-   Build initial MVP against FindAPhD before expanding to individual
    university sites.
-   Implement batching for efficiency with local models or providers
    that offer discounts.
-   Keep one blob per LLM extraction (no chunking of multiple pages into
    one prompt).
-   Consider lightweight validation of generated search queries.
-   Add alignment/funding filtering after extraction.
-   Later: integrate more advanced agent loops (retrying, validation,
    memory).

------------------------------------------------------------------------

## File Purpose

This `agent_plan.md` file summarizes: - The project direction - The
agreed workflow - The components you'll implement - The reasoning behind
each architectural choice

Place it in the **root of your repository** as a reference for
development.
