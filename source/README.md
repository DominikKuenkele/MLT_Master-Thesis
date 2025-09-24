# Source Code Documentation

This directory contains the implementation code for the research on emerging referring expressions through language games.

## Code Structure

The code is organized in the `mlt/` package:

### Root Directory
Core utilities used across all experiments:
- `feature_extractors.py`: Implementations for extracting features from visual scenes
- `image_loader.py`: Utilities for loading and processing CLEVR dataset images
- `shared_models.py`: Common model architectures used across experiments
- `util.py`: Helper functions and utilities
- `test.ipynb` & `visualize.ipynb`: Jupyter notebooks for testing and visualization

### Preexperiments (`preexperiments/`)
Single model experiments serving as baselines to validate the generated datasets and model architectures:
- Validation of dataset generation and bias control
- Testing of individual model components
- Baseline performance metrics
- Model architecture verification before language game implementation

### Language Games (`language_games/`)
Implementation of neural models and datasets for the language game experiments:
- Neural architectures for sender and receiver agents
- Language game implementation and training procedures
- Dataset generation and processing for multi-agent communication
- Analysis tools for emerged referring expressions

## Setup and Installation

1. Install requirements:
```bash
pip install -r requirements.txt
```

2. Set up the environment:
```bash
python -m mlt.extract_features.sh
```

### Datasets
Download and extract the following datasets:
- [CLEVR single](https://nextcloud.dominik-kuenkele.de/s/pqLTRMp9qZXp7Zn)
- [Dale-2](https://nextcloud.dominik-kuenkele.de/s/WMSEdMok962L266)
- [Dale-5](https://nextcloud.dominik-kuenkele.de/s/Dkc7cL5c9RWe8gc)
- [CLEVR color](https://nextcloud.dominik-kuenkele.de/s/foqFo5oJ6Tdgm5x)

### Extract features
For faster training, we can extract features of the raw images with ResNet or VGG and save them in `.h5` files. This is done with `feature_extractors.py`.
Refer to `extract_features.sh` for some usage examples. 
The resulting `.h5` files should be stored in the `features` subfolder for each dataset.

## Running Experiments

### Preexperiments

To run baseline experiments with single models, select model configuration from `preexperiments/train.py` and provide hyperparameters. E.g.:
```bash
python source/mlt/preexperiments/train.py --dataset_base_dir=/path/to/datasets/ --dataset=colour --image_feature_file=resnet_3_no-avgpool_no-fc.h5 --max_samples=10000 --model=dale_attribute_attention_predictor --encoder_out=1500 --encoder_embedding=15 --projection=1000 --epochs=20 --lr=0.0002 --device=cuda --batch_size=32 --out_dir=out/

python source/mlt/preexperiments/train.py --dataset_base_dir=/path/to/datasets/ --dataset=dale-2 --image_feature_file=resnet_3_no-avgpool_no-fc.h5 --max_samples=10000 --model=all_masked_dale_attribute_coordinate_predictor --encoder_out=1500 --encoder_embedding=30  --image_embedding_dimension=1000 --coordinate_classifier_dimension=1024 --epochs=30 --lr=0.0005 --device=cuda --batch_size=32 --out_dir=out/
```

### Language Games

To train agents in language games, select model configuration from `language_games/play.py` and provide hyperparameters. E.g.:
```bash
python source/mlt/language_games/play.py --dataset_base_dir=/path/to/datasets/ --out_dir=out/ --validation_batch_size=256 --validation_batches_per_epoch=8 --save --sender_cell=lstm --receiver_cell=lstm --image_feature_file=resnet_3_no-avgpool_no-fc.h5 --bounding_box_feature_file=bounding_box_resnet_4_avgpool_no-fc.h5 --n_epochs=100 --batch_size=32 --batches_per_epoch=40 --validation_freq=10 --lr=0.0002 --max_samples=10000 --temperature=1 --model=bounding_box_caption_generator --dataset=dale-5 --sender_embedding=100 --sender_hidden=500 --sender_image_embedding=500 --receiver_embedding=100 --receiver_hidden=500 --receiver_image_embedding=100 --receiver_decoder_out=1500 --receiver_decoder_embedding=15 --vocab_size=50 --max_len=4
```

Or specify combinations of different hyperparameters in `language_games/run_experiments.py` and run script.