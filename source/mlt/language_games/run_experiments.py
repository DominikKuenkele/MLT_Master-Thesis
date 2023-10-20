import itertools
import subprocess

options = [
    # "--dataset_base_dir=/scratch/guskunkdo",
    "--dataset_base_dir=/home/dominik/Development/",
    "--n_epochs=30",
    "--batch_size=2",
    "--batches_per_epoch=1",
    "--lr=0.0002",
    "--feature_file=resnet_3_no-avgpool_no-fc.h5",
    "--max_samples=10000",
    "--device=cuda",
    "--model=discriminator",
    "--mode=gs",
    "--sender_cell=lstm",
    "--receiver_cell=lstm",
    "--save=True",
    # "--out_dir=/scratch/guskunkdo/out/",
    "--out_dir=out/",
    # -- model specifics --
    "--sender_embedding=500",
    # "--sender_encoder_dim=",
    "--receiver_embedding=",
    # "--receiver_decoder_out_dim=",
    # "--coordinate_classifier_dimension=",
]

variables = {
    "--dataset": ["dale-2", "dale-5", "colour"],
    "--sender_hidden": [100, 500, 1000],
    "--receiver_hidden": [15, 30],
    "--temperature": [1, 3, 5, 10],
    "--vocab_size": [1, 10, 16, 50, 100],
    "--max_len": [1, 2, 3, 4, 5, 6],
}

for index, combination in enumerate(itertools.product(*variables.values())):
    save_appendix = "_".join(str(i) for i in combination[1:])
    subprocess.run(
        [
            "python",
            "source/mlt/language_games/play.py",
            *options,
            *[
                f"{option}={value}"
                for option, value in zip(variables.keys(), combination)
            ],
            f"--save_appendix={save_appendix}",
        ],
        check=False,
    )