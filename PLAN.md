We are re-building Petey, a framework for extracting data from PDF forms. The goal is to make it fully offline, without frontier AI or external API calls. It's not quite there yet.

It has been through several iterations and exists in a collection of poorly aligned repos. The purpose of this repo is to reconstitute the useful parts of the older versions into a new, cleaner repo (this one).

The old code is currently in ~/Documents/code/petey-master .

Petey works by creating a .bpt ("blueprint") file (spec provided in BPT SPEC v1.1.md), which is a .yaml file with the location, name, data type and validation information etc. for every field in a form. Petey's target is standardized forms (tax, DMV, immigration etc.), where once a .bpt is generated, it can be used forever to extract data from a filled version of that form.

The plan is to launch with 200+ blueprints.

Petey also includes .bpt generation code. There are three routes:
- programmatic (the code in this repo), which uses the visual representation of the form
- metadata-based (in the old repo), which uses the AcroForm widgets and external data sets (mostly Sensible)
- VLM (in the old repo), which uses fronter AI

For a given form, Petey creates a draft .bpt, then uses alternate methods to generates synthetic data to create draft forms. Petey then extracts the data from the draft forms and compares the output to the expected output (ie the original synthetic data), and checks for errors based on an established error taxonomy with canonical fixes. It then fixes the draft .bpt and repeats the process until the output matches the synthetic data.

You can see the problem here wrt input and output. The original plan was:
1) use metadata to create the .bpt
2) use a VLM to more directly infer the form content
3) use the VLM info to generate synthetic data
4) extract with Petey using the .bpt
5) compare, fix, iterate

But I overestimated how well the VLM could map a form, and whether it would reliably produce the same data. This still needs to be sorted, but I decided to try to build a programmatic approach first, so we could have three versions of the form to compare. Now I have that (this repo), so we need to integrate the three sources.

Your job is to:
1) Extract the useful code from petey-master
2) Evaluate, dissect and standardize the outputs from the VLM approach
3) Make a strategy to build and validate .bpt using the three routes. (We can optimize this and build out the error taxonomy later ... this is about structure and integrating the three routes.)

Every form I have is in ./source_pdfs. All of the earlier work, including the existing .bpt files, version history, the sensible data, permissions and external keys should be in petey-master.