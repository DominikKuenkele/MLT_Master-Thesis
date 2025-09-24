# Emergence of Referring Expressions through Language Games

This repository contains the research code and thesis documents for exploring how referring expressions emerge in artificial neural agents through language games, and how these expressions compare to those found in natural languages like English.

## Abstract

There has been a recent focus on how neural agents in language games ground referring expressions in visual 3D-scenes.
This thesis explores when referring expressions emerge and if they align with referring expression found in natural languages like English.
For this, multiple new artificial datasets  based on the CLEVR dataset are generated to control precisely for the bias included in the visual scenes, namely the attributes of the target object and distractors.
The datasets and their controlled biases are validated in a series of reference expression generation and comprehension tasks.
A sender and a receiver are playing language games in which they need communicate referring expressions to solve the same tasks.
For many tasks, they are able to successfully ground referring expressions in their own emerged language.
An analysis of the emerged languages shows that the emerged referring expressions are aligned very few with natural language referring expressions.
However, they share certain features like an incremental approach in which some attributes are consistently used more often than others.

## Repository Structure

- `thesis/`: Contains the full thesis document and related LaTeX files
- `source/`: Contains the implementation code for the experiments
  - See [source/README.md](source/README.md) for detailed code documentation
- `iwcs-2025/`: IWCS 2025 conference paper materials
- `larp-2025/`: LARP 2025 conference presentation
- `semdial-2023/`: SemDial 2023 conference materials

## Implementation

The implementation details and instructions for running the experiments can be found in the source code documentation. Please refer to the [source/README.md](source/README.md) file for:

- Environment setup
- Dataset generation
- Model training
- Experiment reproduction
- Analysis tools

## Citation

If you use this code or research, please cite one of the following:

### IWCS 2025
```bibtex
@inproceedings{kunkele-dobnik-2025-learning,
    title = "Learning to Refer: How Scene Complexity Affects Emergent Communication in Neural Agents",
    author = {K{\"u}nkele, Dominik  and
      Dobnik, Simon},
    editor = "Evang, Kilian  and
      Kallmeyer, Laura  and
      Pogodalla, Sylvain",
    booktitle = "Proceedings of the 16th International Conference on Computational Semantics",
    month = sep,
    year = "2025",
    address = {D{\"u}sseldorf, Germany},
    publisher = "Association for Computational Linguistics",
    url = "https://preview.aclanthology.org/iwcs-25-ingestion/2025.iwcs-1.26/",
    pages = "299--307",
    ISBN = "979-8-89176-316-6",
}
```

### Master Thesis

```bibtex
@mastersthesis{kunkele2023emergence,
    title={Emergence of referring expressions through language games},
    author={K{"u}nkele, Dominik},
    year={2023},
    school={University of Gothenburg},
    type={Master's Thesis}
}
```

### Semdial 2023
```bibtex
@inproceedings{kunkele-dobnik-2023-referring,
    title = "Referring as a collaborative process: learning to ground language through language games",
    author = {K{\"u}nkele, Dominik  and
      Dobnik, Simon},
    booktitle = "Proceedings of the 27th Workshop on the Semantics and Pragmatics of Dialogue - Poster Abstracts",
    month = aug,
    year = "2023",
    address = "Maribor, Slovenia",
    publisher = "SEMDIAL",
    url = "http://semdial.org/anthology/Z23-Kunkele_semdial_0020.pdf",
}
```