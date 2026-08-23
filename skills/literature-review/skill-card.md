## Description: <br>
Assistance with writing literature reviews by searching for academic sources via Semantic Scholar, OpenAlex, Crossref and PubMed APIs. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[weird-aftertaste](https://clawhub.ai/user/weird-aftertaste) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers, researchers, and writing assistants use this skill to find papers on a topic, retrieve DOI or paper metadata, compare academic search sources, and draft literature review sections with citations. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Literature queries, optional contact email, and optional API keys may be sent to Semantic Scholar, OpenAlex, Crossref, and PubMed. <br>
Mitigation: Use non-sensitive queries, a dedicated low-privilege API key, and a non-sensitive contact email when configuring the skill. <br>
Risk: Search results and synthesized review text can contain incomplete, outdated, or misleading academic claims. <br>
Mitigation: Cross-reference DOI or PMID records and review source abstracts before relying on citations or drafted prose. <br>


## Reference(s): <br>
- [ClawHub Skill Page](https://clawhub.ai/weird-aftertaste/skills/literature-review) <br>
- [Semantic Scholar Graph API](https://api.semanticscholar.org/graph/v1) <br>
- [OpenAlex API](https://api.openalex.org) <br>
- [Crossref Works API](https://api.crossref.org/works) <br>
- [PubMed E-utilities API](https://eutils.ncbi.nlm.nih.gov/entrez/eutils) <br>


## Skill Output: <br>
**Output Type(s):** [Text, Markdown, Code, Shell commands, Configuration, Guidance] <br>
**Output Format:** [JSON search results and Markdown guidance with inline shell commands] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Academic metadata may include DOI, PMID, title, year, authors, abstract, venue, citation count, and source; optional API keys and contact email settings can affect external API access.] <br>

## Skill Version(s): <br>
1.2.0 (source: frontmatter and server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
