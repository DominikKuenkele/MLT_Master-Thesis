import argparse
import hashlib
import os
import sys
from dataclasses import dataclass, field
from typing import Callable

import torch
from mlt.feature_extractors import DummyFeatureExtractor, ResnetFeatureExtractor
from mlt.image_loader import ClevrImageLoader, FeatureImageLoader
from mlt.preexperiments.data_readers import (
    AllObjectsImageMasker,
    AttentionPredictorDataset,
    BoundingBoxCaptioningDataset,
    BoundingBoxClassifierDataset,
    CaptionGeneratorDataset,
    CoordinatePredictorDataset,
    DaleCaptionAttributeEncoder,
    MaskPredictorDataset,
    OneHotAttributeEncoder,
    OneHotGeneratorDataset,
    SingleObjectImageMasker,
)
from mlt.preexperiments.losses import pixel_loss
from mlt.preexperiments.models import (
    AttributeCoordinatePredictor,
    AttributeLocationCoordinatePredictor,
    BoundingBoxAttributeClassifier,
    BoundingBoxCaptionGenerator,
    BoundingBoxClassifier,
    CaptionDecoder,
    CaptionGenerator,
    CoordinatePredictor,
    DaleAttributeAttentionPredictor,
    DaleAttributeCoordinatePredictor,
    MaskedCaptionGenerator,
    MaskedCoordinatePredictor,
    MaskedDaleAttributeCoordinatePredictor,
    MaskedMaskPredictor,
    OneHotGenerator,
    RandomCoordinatePredictor,
)
from mlt.preexperiments.save import (
    BoundingBoxOutputProcessor,
    CaptionOutputProcessor,
    ModelSaver,
    MultiHotPredictorProcessor,
    PixelOutputProcessor,
    StandardOutputProcessor,
)
from mlt.preexperiments.test import (
    AttentionPredictorTester,
    BoundingBoxClassifierTester,
    CaptionGeneratorTester,
    CoordinatePredictorTester,
    DummyTester,
    OneHotGeneratorTester,
    Tester,
)
from mlt.shared_models import ClevrImageEncoder, CoordinateClassifier, MaskPredictor
from mlt.util import Persistor, colors, get_model_params, set_model_params
from torch import nn, optim
from torch.nn import Module
from torch.utils.data import DataLoader, Dataset, random_split
from torcheval.metrics import Mean
from torchvision.models import ResNet101_Weights


@dataclass
class ModelDefinition:
    dataset: Dataset
    dataset_args: dict
    preprocess: Callable
    model: Module
    model_args: dict
    loss_function: Callable
    tester: Tester
    output_processor: StandardOutputProcessor
    output_processor_args: dict

    # optional
    caption_decoder_args: dict = field(default_factory=dict)


models = {
    "coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={},
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=CoordinatePredictor,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "coordinate_classifier": CoordinateClassifier,
        },
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    # not working at the moment
    # "coordinate_predictor_scratch": ModelDefinition(
    #     dataset=CoordinatePredictorDataset,
    #     dataset_args={},
    #     preprocess=PreprocessScratch(250),
    #     model=CoordinatePredictor,
    #     model_args={
    #         "feature_extractor": ResnetFeatureExtractor(
    #             pretrained=False, fine_tune=True
    #         )
    #     },
    #     loss_function=pixel_loss,
    #     tester=CoordinatePredictorTester,
    #     output_processor=PixelOutputProcessor,
    #     output_processor_args={
    #         "output_fields": ("image_id", "x", "y", "target_x", "target_y")
    #     },
    # ),
    "attribute_coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={"attribute_encoder": OneHotAttributeEncoder()},
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=AttributeCoordinatePredictor,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "coordinate_classifier": CoordinateClassifier,
        },
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "dale_attribute_coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={
            "attribute_encoder": DaleCaptionAttributeEncoder(
                padding_position=DaleCaptionAttributeEncoder.PaddingPosition.APPEND,
                reversed_caption=False,
            )
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=DaleAttributeCoordinatePredictor,
        model_args={
            "encoder_vocab_size": len(DaleCaptionAttributeEncoder.vocab),
            "encoder_embedding": len(DaleCaptionAttributeEncoder.vocab),
            "encoder_encoder_out": len(DaleCaptionAttributeEncoder.vocab),
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "coordinate_classifier": CoordinateClassifier,
        },
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "all_masked_dale_attribute_coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={
            "attribute_encoder": DaleCaptionAttributeEncoder(
                padding_position=DaleCaptionAttributeEncoder.PaddingPosition.APPEND,
                reversed_caption=False,
            ),
            "image_masker": AllObjectsImageMasker(),
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=MaskedDaleAttributeCoordinatePredictor,
        model_args={
            "encoder_vocab_size": len(DaleCaptionAttributeEncoder.vocab),
            "encoder_embedding": len(DaleCaptionAttributeEncoder.vocab),
            "encoder_out": len(DaleCaptionAttributeEncoder.vocab),
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "masked_image_encoder": ClevrImageEncoder(
                feature_extractor=ResnetFeatureExtractor(
                    pretrained=True,
                    avgpool=False,
                    fc=False,
                    fine_tune=False,
                    number_blocks=3,
                ),
                max_pool=True,
            ),
            "coordinate_classifier": CoordinateClassifier,
        },
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "attribute_location_coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={
            "attribute_encoder": OneHotAttributeEncoder(),
            "encode_locations": True,
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=AttributeLocationCoordinatePredictor,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "coordinate_classifier": CoordinateClassifier,
        },
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "masked_coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={"image_masker": SingleObjectImageMasker()},
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=MaskedCoordinatePredictor,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "masked_image_encoder": ClevrImageEncoder(
                feature_extractor=ResnetFeatureExtractor(
                    pretrained=True,
                    avgpool=False,
                    fc=False,
                    fine_tune=False,
                    number_blocks=3,
                ),
                max_pool=True,
            ),
            "coordinate_classifier": CoordinateClassifier,
        },
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "all_masked_coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={"image_masker": AllObjectsImageMasker()},
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=MaskedCoordinatePredictor,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "masked_image_encoder": ClevrImageEncoder(
                feature_extractor=ResnetFeatureExtractor(
                    pretrained=True,
                    avgpool=False,
                    fc=False,
                    fine_tune=False,
                    number_blocks=3,
                ),
                max_pool=True,
            ),
            "coordinate_classifier": CoordinateClassifier,
        },
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "random_coordinate_predictor": ModelDefinition(
        dataset=CoordinatePredictorDataset,
        dataset_args={},
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=RandomCoordinatePredictor,
        model_args={},
        loss_function=pixel_loss,
        tester=CoordinatePredictorTester,
        output_processor=PixelOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "masked_mask_predictor": ModelDefinition(
        dataset=MaskPredictorDataset,
        dataset_args={"image_masker": SingleObjectImageMasker()},
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=MaskedMaskPredictor,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "masked_image_encoder": ClevrImageEncoder(
                feature_extractor=ResnetFeatureExtractor(
                    pretrained=True,
                    avgpool=False,
                    fc=False,
                    fine_tune=False,
                    number_blocks=3,
                ),
                max_pool=True,
            ),
            "mask_predictor": MaskPredictor,
        },
        loss_function=nn.BCELoss(),
        tester=DummyTester,
        output_processor=StandardOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "x", "y", "target_x", "target_y")
        },
    ),
    "dale_attribute_attention_predictor": ModelDefinition(
        dataset=AttentionPredictorDataset,
        dataset_args={
            "attribute_encoder": DaleCaptionAttributeEncoder(
                padding_position=DaleCaptionAttributeEncoder.PaddingPosition.APPEND,
                reversed_caption=False,
            ),
            "number_regions": 14,
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=DaleAttributeAttentionPredictor,
        model_args={
            "encoder_vocab_size": len(DaleCaptionAttributeEncoder.vocab),
            "encoder_embedding": len(DaleCaptionAttributeEncoder.vocab),
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=False
            ),
        },
        loss_function=nn.BCELoss(),
        tester=AttentionPredictorTester,
        output_processor=MultiHotPredictorProcessor,
        output_processor_args={
            "output_fields": ("image_id", "region", "target_region")
        },
    ),
    "bounding_box_classifier": ModelDefinition(
        dataset=BoundingBoxClassifierDataset,
        dataset_args={},
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=BoundingBoxClassifier,
        model_args={},
        loss_function=nn.CrossEntropyLoss(),
        tester=BoundingBoxClassifierTester,
        output_processor=BoundingBoxOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "bounding_box", "target_bounding_box")
        },
    ),
    "bounding_box_classifier_attributes": ModelDefinition(
        dataset=BoundingBoxClassifierDataset,
        dataset_args={
            "attribute_encoder": OneHotAttributeEncoder(),
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=BoundingBoxAttributeClassifier,
        model_args={},
        loss_function=nn.CrossEntropyLoss(),
        tester=BoundingBoxClassifierTester,
        output_processor=BoundingBoxOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "bounding_box", "target_bounding_box")
        },
    ),
    "bounding_box_caption_generator": ModelDefinition(
        dataset=BoundingBoxCaptioningDataset,
        dataset_args={
            "captioner": DaleCaptionAttributeEncoder(
                padding_position=DaleCaptionAttributeEncoder.PaddingPosition.PREPEND,
                reversed_caption=False,
            ),
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=BoundingBoxCaptionGenerator,
        model_args={
            "caption_decoder": CaptionDecoder,
            "encoded_sos": DaleCaptionAttributeEncoder.get_encoded_word(
                DaleCaptionAttributeEncoder.SOS_TOKEN
            ),
        },
        loss_function=nn.CrossEntropyLoss(),
        tester=CaptionGeneratorTester,
        output_processor=CaptionOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "caption", "target_caption")
        },
    ),
    "caption_generator": ModelDefinition(
        dataset=CaptionGeneratorDataset,
        dataset_args={
            "captioner": DaleCaptionAttributeEncoder(
                padding_position=DaleCaptionAttributeEncoder.PaddingPosition.PREPEND,
                reversed_caption=False,
            )
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=CaptionGenerator,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "caption_decoder": CaptionDecoder,
            "encoded_sos": DaleCaptionAttributeEncoder.get_encoded_word(
                DaleCaptionAttributeEncoder.SOS_TOKEN
            ),
        },
        loss_function=nn.CrossEntropyLoss(),
        tester=CaptionGeneratorTester,
        output_processor=CaptionOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "caption", "target_caption")
        },
    ),
    "masked_caption_generator": ModelDefinition(
        dataset=CaptionGeneratorDataset,
        dataset_args={
            "captioner": DaleCaptionAttributeEncoder(
                padding_position=DaleCaptionAttributeEncoder.PaddingPosition.PREPEND,
                reversed_caption=False,
            ),
            "image_masker": SingleObjectImageMasker(),
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=MaskedCaptionGenerator,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "masked_image_encoder": ClevrImageEncoder(
                feature_extractor=ResnetFeatureExtractor(
                    pretrained=True,
                    avgpool=False,
                    fc=False,
                    fine_tune=False,
                    number_blocks=3,
                ),
                max_pool=True,
            ),
            "caption_decoder": CaptionDecoder,
            "encoded_sos": DaleCaptionAttributeEncoder.get_encoded_word(
                DaleCaptionAttributeEncoder.SOS_TOKEN
            ),
        },
        loss_function=nn.CrossEntropyLoss(),
        tester=CaptionGeneratorTester,
        output_processor=CaptionOutputProcessor,
        output_processor_args={
            "output_fields": ("image_id", "caption", "target_caption")
        },
    ),
    "one_hot_generator": ModelDefinition(
        dataset=OneHotGeneratorDataset,
        dataset_args={
            "attribute_encoder": DaleCaptionAttributeEncoder(
                padding_position=DaleCaptionAttributeEncoder.PaddingPosition.PREPEND,
                reversed_caption=False,
            ),
            "target_attribute_encoder": OneHotAttributeEncoder(),
        },
        preprocess=ResNet101_Weights.IMAGENET1K_V2.transforms(),
        model=OneHotGenerator,
        model_args={
            "image_encoder": ClevrImageEncoder(
                feature_extractor=DummyFeatureExtractor(), max_pool=True
            ),
            "encoder_vocab_size": len(DaleCaptionAttributeEncoder.vocab),
            "encoder_embedding": len(DaleCaptionAttributeEncoder.vocab),
            "encoder_out": len(DaleCaptionAttributeEncoder.vocab),
            "number_attributes": 13,
        },
        loss_function=nn.BCELoss(),
        tester=OneHotGeneratorTester,
        output_processor=MultiHotPredictorProcessor,
        output_processor_args={"output_fields": ("image_id", "predicted", "target")},
    ),
}

# names of the datasets and their foldernames
datasets = {
    "dale-2": "clevr-images-unambigous-dale-two",
    "dale-5": "clevr-images-unambigous-dale",
    "single": "clevr-images-random-single",
    "colour": "clevr-images-unambigous-colour",
}


def print_gpu_allocation():
    print(f"GPU: {torch.cuda.memory_allocated()/(1024**3):.2f}GB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # -- DATASET --
    parser.add_argument(
        "--dataset_base_dir",
        type=str,
        help="Path to the base directory of all datasets",
    )
    parser.add_argument("--dataset", choices=datasets.keys(), help="datasets, to load")
    parser.add_argument(
        "--image_feature_file",
        type=str,
        default=None,
        help="Name of the hd5 file containing extracted image features",
    )
    parser.add_argument(
        "--bounding_box_feature_file",
        type=str,
        default=None,
        help="Name of the hd5 file containing extracted image features",
    )
    parser.add_argument(
        "--checkpoint_path",
        type=str,
        default=None,
        help="Path to a saved model state dict",
    )
    parser.add_argument(
        "--max_samples", type=int, default=None, help="max samples to load"
    )

    # -- MODEL --
    parser.add_argument(
        "--model",
        choices=models.keys(),
        help="model to load",
    )
    parser.add_argument("--decoder_out", type=int)
    parser.add_argument("--encoder_out", type=int)
    parser.add_argument("--encoder_embedding", type=int)
    parser.add_argument("--image_embedding", type=int)
    parser.add_argument("--coordinate_classifier_dimension", type=int)
    parser.add_argument("--mask_predictor_dimension", type=int)
    parser.add_argument("--projection", type=int)

    # -- TRAINING --
    parser.add_argument("--epochs", type=int, default=10, help="number of epochs")
    parser.add_argument("--lr", type=float, default=0.002, help="learning rate")
    parser.add_argument("--device", type=str, default="cuda", help="cpu or cuda")
    parser.add_argument("--batch_size", type=int, default=32, help="batch size")

    # -- SAVING --
    parser.add_argument(
        "--out_dir",
        type=str,
        default="out/",
        help="directory, where the output should be saved",
    )
    parser.add_argument(
        "--save_model",
        type=bool,
        default=False,
        help="if model should be saved",
    )

    args = parser.parse_args()
    print(args)

    if args.device == "cpu":
        device = torch.device("cpu")
    elif args.device == "cuda":
        device = torch.device("cuda")
    else:
        raise AttributeError("Device must be cpu or cuda")

    image_dir = os.path.join(args.dataset_base_dir, datasets[args.dataset], "images/")
    scene_json_dir = os.path.join(
        args.dataset_base_dir, datasets[args.dataset], "scenes/"
    )

    model_name = models[args.model]

    if args.image_feature_file is not None:
        image_feature_file = os.path.join(
            args.dataset_base_dir,
            datasets[args.dataset],
            "features",
            args.image_feature_file,
        )
        image_loader = FeatureImageLoader(
            feature_file=image_feature_file, image_dir=image_dir
        )
    else:
        image_loader = ClevrImageLoader(
            image_dir=image_dir,
            preprocess=model_name.preprocess,
        )

    if args.bounding_box_feature_file is not None:
        bounding_box_feature_file = os.path.join(
            args.dataset_base_dir,
            datasets[args.dataset],
            "features",
            args.bounding_box_feature_file,
        )
        bounding_box_loader = FeatureImageLoader(
            feature_file=bounding_box_feature_file, image_dir=image_dir
        )
    else:
        bounding_box_loader = None

    dataset_args = {
        "scenes_json_dir": scene_json_dir,
        "image_loader": image_loader,
        "bounding_box_loader": bounding_box_loader,
        "max_number_samples": args.max_samples,
        **model_name.dataset_args,
    }

    dataset_identifier = hashlib.sha256(
        str(f"{model_name.dataset.__name__}({dataset_args})").encode()
    ).hexdigest()
    dataset_dir = os.path.join(args.out_dir, "datasets")
    dataset_file = os.path.join(dataset_dir, f"{dataset_identifier}.h5")
    persistor = Persistor(dataset_file)
    if os.path.exists(dataset_file):
        print(f"Loading dataset {dataset_identifier}...", end="\r")
        dataset = persistor.load(model_name.dataset)
        print(f"Dataset {dataset_identifier} loaded.   ")
    else:
        dataset = model_name.dataset.load(
            **dataset_args,
            persistor=Persistor(dataset_file),
        )
        print(f"Dataset {dataset_identifier} saved.   ")

    train_dataset_length = int(0.8 * len(dataset))
    test_dataset_length = len(dataset) - train_dataset_length
    train_dataset, test_dataset = random_split(
        dataset, (train_dataset_length, test_dataset_length)
    )

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=1
    )
    test_loader = DataLoader(
        test_dataset, batch_size=args.batch_size, shuffle=True, num_workers=1
    )

    output_processor = model_name.output_processor(
        dataset=dataset, **model_name.output_processor_args
    )

    tester = model_name.tester()

    model_params = get_model_params(model_name.model, args)
    model_args = set_model_params(model_name.model_args, model_params)

    appendices = []
    params_check = True
    for param, value in sorted(model_args.items()):
        if param not in args:
            continue

        if value is None:
            color = colors.RED
            params_check = False
        else:
            color = colors.GREEN

        appendices.append((param, value))

        print(f"{param} = {color}{value}{colors.ENDC}")

    if not params_check:
        sys.exit()

    if "caption_decoder" in model_args.keys():
        model_args["caption_decoder"] = model_args["caption_decoder"](
            decoder_embedding=args.embedding_dim,
            decoder_out=args.decoder_out_dim,
            decoder_vocab_size=len(DaleCaptionAttributeEncoder.vocab),
        )

    if "coordinate_classifier" in model_args.keys():
        model_args["coordinate_classifier"] = model_args["coordinate_classifier"](
            coordinate_classifier_dimension=args.coordinate_classifier_dimension
        )

    if "mask_predictor" in model_args.keys():
        model_args["mask_predictor"] = model_args["mask_predictor"](
            mask_predictor_dimension=args.mask_predictor_dimension
        )

    model = model_name.model(**model_args).to(device)

    if args.checkpoint_path is not None:
        model.load_state_dict(torch.load(args.checkpoint_path))

    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    loss_function = model_name.loss_function

    log = [str(args), str(model), f"appendix: {[param for param, _ in appendices]}"]

    print(f"Batches per epoch: {len(train_loader)}")
    for epoch in range(args.epochs):
        total_loss = Mean(device=device)
        model.train()
        train_outputs = []
        for i, (model_input, ground_truth, image_id) in enumerate(train_loader):
            if isinstance(model_input, list):
                model_input = [t.to(device) for t in model_input]
            else:
                model_input.to(device)
            ground_truth = ground_truth.to(device)

            output = model(model_input)
            train_outputs.extend(
                zip(image_id, output.detach().cpu(), ground_truth.cpu())
            )

            loss = loss_function(output, ground_truth)

            total_loss.update(loss)

            loss_string = f"epoch {epoch}, batch {i}: {total_loss.compute():.4f}"
            print(
                loss_string,
                end="\r",
            )

            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
        print()
        metrics, test_outputs = tester.test(model, test_loader, device)
        print(metrics)
        log.append(loss_string)
        log.append(str(metrics))

    save_appendix = "_".join([str(value) for _, value in appendices])
    model_saver = ModelSaver(
        out_dir=args.out_dir,
        model_name=args.model,
        dataset=args.dataset,
        save_appendix=save_appendix,
        output_processor=output_processor,
    )
    if args.save_model:
        model_saver.save_model(model, f"{model.__class__.__name__}.pth")
    model_saver.save_log(log, "log.txt")
    model_saver.save_output(test_outputs, "test_outputs.csv")
    model_saver.save_output(train_outputs, "train_outputs.csv")
