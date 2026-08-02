# Thesis Template

This is an unofficial thesis template to be used for arbitrary student projects at the Department of Informatics at TUM. It has already been used in numerous successful theses and contains a collection of useful LaTeX tips and tricks. Please note that formatting requirements may change over time, so always verify that the template complies with the current official guidelines.

## Building the PDF

Building a LaTeX document requires multiple compilation passes to resolve citations, references, the table of contents, and other generated content. The following options are available.

### Manual compilation

Compile the document manually by invoking the required tools in the correct order:

```bash
pdflatex main.tex         # First pass to generate auxiliary files
bibtex main.aux           # Generate bibliography
pdflatex main.tex         # Resolve cross references
pdflatex main.tex         # Resolve citations
```

### latexmk (recommended)

`latexmk` automatically determines which compilation steps are required and reruns LaTeX as often as necessary.

```bash
latexmk -pdf main.tex
```

### Continuous compilation (recommended for writing)

For day-to-day writing, it is recommended to let `latexmk` watch the project and automatically rebuild the PDF whenever a source file changes.

Open a terminal in the project directory and run:

```bash
latexmk -pdf -outdir=build -pvc main.tex
```

The `-pvc` (`preview continuously`) option monitors all `.tex`, `.bib`, and other dependent files. Whenever you save a file, the document is automatically recompiled.
Old files in the build folder get automatically rewritten. 

### Viewing the PDF with Zathura

Open a second terminal and start Zathura:

```bash
zathura build/main.pdf
```

Leave both `latexmk` and Zathura running while writing.

Your workflow is then:

1. Edit the document in your editor (e.g. CLion with the TeXiFy plugin).
2. Save the file (`Ctrl+S`).
3. `latexmk` automatically recompiles the document.
4. Zathura automatically reloads the updated PDF.

This provides a live-preview workflow without having to manually rebuild or reopen the PDF.

### IDE

Alternatively, use a LaTeX IDE such as TeXstudio or the TeXiFy plugin for IntelliJ-based IDEs (e.g. CLion or IntelliJ IDEA), which provide syntax highlighting, citation support, and integrated build configurations.

Example using TeXstudio:

```bash
texstudio main.tex
```

Press **F5** to build the document and display the generated PDF.
