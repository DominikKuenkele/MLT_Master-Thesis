import itertools
import json
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import torch
from mlt.image_loader import ImageLoader
from mlt.preexperiments.models import FeatureExtractor
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms
from torchvision.models import ResNet101_Weights


class Attribute(Enum):
    @classmethod
    def names(cls):
        return list(map(lambda a: a.name, cls))


class Shape(Attribute):
    CUBE = 0
    SPHERE = 1
    CYLINDER = 2


class Color(Attribute):
    GRAY = 0
    RED = 1
    BLUE = 2
    GREEN = 3
    BROWN = 4
    PURPLE = 5
    CYAN = 6
    YELLOW = 7


class Size(Attribute):
    SMALL = 0
    LARGE = 1


class PreprocessScratch:
    def __init__(self, image_size):
        self.transform = transforms.Compose(
            [
                transforms.Resize(image_size),
                transforms.PILToTensor(),
                transforms.ConvertImageDtype(torch.float),
            ]
        )
        ratio = 1.5
        self.resize_size = (image_size * ratio, image_size)
        self.crop_size = None

    def __call__(self, image):
        return self.transform(image)


class BoundingBoxClassifierDataset(Dataset):
    """
    Input:
     - bounding boxes of all objects

    Ouput:
     - index of target bounding box
    """

    def __init__(
        self,
        scenes_json_dir,
        image_path,
        max_number_samples,
        feature_extractor: FeatureExtractor = None,
        preprocess=ResNet101_Weights.DEFAULT.transforms(),
        device=torch.device("cpu"),
    ) -> None:
        super().__init__()

        if feature_extractor is not None:
            feature_extractor = feature_extractor.to(device)
            feature_extractor.eval()

        self.samples = []

        scenes = os.listdir(scenes_json_dir)
        print("sampling scenes...")
        selected_scenes = random.sample(scenes, max_number_samples)

        for scene_index, scene_file in enumerate(selected_scenes):
            if scene_index % 50 == 0:
                print(f"processing scene {scene_index}...", end="\r")

            with open(
                os.path.join(scenes_json_dir, scene_file), "r", encoding="utf-8"
            ) as f:
                scene = json.load(f)

            image = Image.open(image_path + scene["image_filename"]).convert("RGB")

            bounding_boxes = self._get_bounding_boxes(image, scene, preprocess)

            if feature_extractor is not None:
                with torch.no_grad():
                    bounding_boxes = [
                        feature_extractor(bounding_box.to(device).unsqueeze(dim=0))
                        .squeeze(dim=0)
                        .cpu()
                        for bounding_box in bounding_boxes
                    ]

            target_object = scene["groups"]["target"][0]
            enumerated = list(enumerate(bounding_boxes))
            random.shuffle(enumerated)

            input_boxes = torch.stack([bounding_box for _, bounding_box in enumerated])
            indices, _ = zip(*enumerated)
            target_index = torch.tensor(indices.index(target_object))

            self.samples.append(
                (input_boxes, target_index, scene_file.removesuffix(".json"))
            )
        print()
        print("loaded data.")

    def _get_bounding_boxes(self, image, scene, preprocess):
        BOUNDING_BOX_SIZE = image.size[0] / 5

        object_bounding_boxes = []
        for obj in scene["objects"]:
            x_center, y_center, _ = obj["pixel_coords"]
            bounding_box = image.crop(
                (
                    x_center - BOUNDING_BOX_SIZE / 2,
                    y_center - BOUNDING_BOX_SIZE / 2,
                    x_center + BOUNDING_BOX_SIZE / 2,
                    y_center + BOUNDING_BOX_SIZE / 2,
                )
            )
            object_bounding_boxes.append(preprocess(bounding_box))

        # magic number 10 (max objects in scene)
        object_bounding_boxes.extend(
            [torch.zeros_like(object_bounding_boxes[0])]
            * (10 - len(object_bounding_boxes))
        )

        return object_bounding_boxes

    def __getitem__(self, index):
        return self.samples[index]

    def __len__(self) -> int:
        return len(self.samples)


class Captioner(ABC):
    @abstractmethod
    def caption(self, scene, object_index):
        ...

    @classmethod
    @abstractmethod
    def get_encoded_word(cls, word):
        ...

    @classmethod
    @abstractmethod
    def get_decoded_word(cls, search_index):
        ...


class AttributeEncoder(ABC):
    @abstractmethod
    def encode(self, scene, object_index):
        ...


class OneHotAttributeEncoder(AttributeEncoder):
    def encode(self, scene, object_index):
        color_tensor = self._one_hot_encode(
            Color, scene["objects"][object_index]["color"]
        )
        shape_tensor = self._one_hot_encode(
            Shape, scene["objects"][object_index]["shape"]
        )
        size_tensor = self._one_hot_encode(Size, scene["objects"][object_index]["size"])

        return torch.cat((color_tensor, shape_tensor, size_tensor))

    def _one_hot_encode(self, attribute: Enum, value: str):
        tensor = torch.zeros(len(attribute))
        tensor[attribute[value.upper()].value] = 1

        return tensor


class DaleCaptionAttributeEncoder(AttributeEncoder, Captioner):
    class PaddingPosition(Enum):
        PREPEND = 0
        APPEND = 1

    PAD_TOKEN = "<pad>"
    SOS_TOKEN = "<sos>"

    # class variable, because vocab is static
    vocab = {
        word: index
        for index, word in enumerate(
            list(
                [
                    PAD_TOKEN,
                    SOS_TOKEN,
                    *[
                        word.lower()
                        for word in [*Size.names(), *Color.names(), *Shape.names()]
                    ],
                ]
            )
        )
    }

    def __init__(
        self, padding_position: PaddingPosition, reversed_caption: bool
    ) -> None:
        super().__init__()
        self.padding_position = padding_position
        self.reversed_caption = reversed_caption

    def encode(self, scene, object_index):
        target_shape = scene["objects"][object_index]["shape"]
        target_color = scene["objects"][object_index]["color"]
        target_size = scene["objects"][object_index]["size"]

        caption = [target_shape]
        remaining_objects = [
            obj for obj in scene["objects"] if obj["shape"] == target_shape
        ]

        if len(remaining_objects) > 1:
            caption.insert(0, target_color)
            remaining_objects = [
                obj for obj in remaining_objects if obj["color"] == target_color
            ]

            if len(remaining_objects) > 1:
                caption.insert(0, target_size)

        encoded_caption = [self.vocab[word] for word in caption]
        if self.reversed_caption:
            encoded_caption.reverse()

        number_of_attributes = 3
        padding = [self.vocab[self.PAD_TOKEN]] * (
            number_of_attributes - len(encoded_caption)
        )
        if self.padding_position == self.PaddingPosition.APPEND:
            encoded_caption.extend(padding)
        elif self.padding_position == self.PaddingPosition.PREPEND:
            encoded_caption[:0] = padding

        return torch.tensor(encoded_caption)

    def caption(self, scene, object_index):
        encoding = self.encode(scene, object_index)

        return torch.cat(
            (torch.tensor(self.vocab[self.SOS_TOKEN]).unsqueeze(0), encoding)
        )

    @classmethod
    def get_encoded_word(cls, word):
        return cls.vocab[word]

    @classmethod
    def get_decoded_word(cls, search_index):
        for word, index in cls.vocab.items():
            if index == search_index:
                return word

        raise AttributeError("no word found with this index")


class CoordinateEncoder:
    def __init__(self, preprocess) -> None:
        self.preprocess = preprocess

    def get_object_coordinates(self, object_index, scene, image_size):
        x, y, _ = scene["objects"][object_index]["pixel_coords"]
        x, y = self._recalculate_coordinates(image_size, (x, y))

        return x, y

    def get_locations(self, scene, image_size):
        locations = []
        for index, _ in enumerate(scene["objects"]):
            x, y = self.get_object_coordinates(index, scene, image_size)
            locations.append(torch.tensor([x, y]))
        locations.extend([torch.zeros_like(locations[0])] * (10 - len(locations)))
        random.shuffle(locations)

        return locations

    def _recalculate_coordinates(self, image_size, object_pixels):
        old_x, old_y = object_pixels
        image_x, image_y = image_size

        if len(self.preprocess.resize_size) == 1:
            new_image_x = self.preprocess.resize_size[0]
            new_image_y = self.preprocess.resize_size[0]
        else:
            new_image_x, new_image_y = self.preprocess.resize_size

        new_x = int(old_x * (new_image_x / image_x))
        new_y = int(old_y * (new_image_y / image_y))

        if self.preprocess.crop_size is not None:
            new_x = int(new_x - ((new_image_x - self.preprocess.crop_size[0]) / 2))
            new_y = int(new_y - ((new_image_y - self.preprocess.crop_size[0]) / 2))

        return new_x, new_y


class ImageMasker(ABC):
    @abstractmethod
    def get_masked_image(self, image, scene, target_object):
        ...


class BasicImageMasker(ImageMasker):
    def get_masked_image(self, image, scene, target_object):
        masked_image = image.copy()
        MASK_SIZE = masked_image.size[0] / 5
        x_center, y_center, _ = scene["objects"][target_object]["pixel_coords"]
        pixels = masked_image.load()

        for i, j in itertools.product(
            range(masked_image.size[0]), range(masked_image.size[1])
        ):
            if (
                i < x_center - MASK_SIZE
                or i > x_center + MASK_SIZE
                or j < y_center - MASK_SIZE
                or j > y_center + MASK_SIZE
            ):
                pixels[i, j] = (0, 0, 0)
            else:
                pixels[i, j] = (255, 255, 255)

        return masked_image


@dataclass
class CoordinatePredictorSample:
    image_id: str
    image: torch.Tensor

    # target
    target_pixels: torch.Tensor

    # addtional (optional) information
    attribute_tensor: torch.Tensor = torch.tensor(0)
    locations: torch.Tensor = torch.tensor(0)
    masked_image: torch.Tensor = torch.tensor(0)


class CoordinatePredictorDataset(Dataset):
    """
    Input:
     - image
     - attributes (optional)
     - center coordinates of all objects (optional)
     - masked image

    Ouput:
     - x and y coordinate of target object
    """

    def __init__(
        self,
        scenes_json_dir,
        image_loader: ImageLoader,
        max_number_samples,
        attribute_encoder: AttributeEncoder = None,
        encode_locations=False,
        image_masker: ImageMasker = None,
        preprocess=ResNet101_Weights.DEFAULT.transforms(),
    ) -> None:
        super().__init__()

        coordinate_encoder = CoordinateEncoder(preprocess)

        self.samples: list[CoordinatePredictorSample] = []

        scenes = os.listdir(scenes_json_dir)
        print("sampling scenes...")
        selected_scenes = random.sample(scenes, max_number_samples)

        for scene_index, scene_file in enumerate(selected_scenes):
            if scene_index % 50 == 0:
                print(f"processing scene {scene_index}...", end="\r")

            with open(
                os.path.join(scenes_json_dir, scene_file), "r", encoding="utf-8"
            ) as f:
                scene = json.load(f)

            image_id = scene_file.removesuffix(".json")
            image, processed_image, image_size = image_loader.get_image(image_id)

            target_object = scene["groups"]["target"][0]
            target_x, target_y = coordinate_encoder.get_object_coordinates(
                target_object,
                scene,
                image_size,
            )

            sample = CoordinatePredictorSample(
                image_id=image_id,
                image=processed_image,
                target_pixels=torch.tensor([target_x, target_y]),
            )

            if attribute_encoder is not None:
                sample.attribute_tensor = attribute_encoder.encode(scene, target_object)

            if encode_locations:
                sample.locations = torch.cat(
                    coordinate_encoder.get_locations(scene, image_size)
                )

            if image_masker is not None:
                sample.masked_image = preprocess(
                    image_masker.get_masked_image(image, scene, target_object)
                )

            self.samples.append(sample)
        print()
        print("loaded data.")

    def __getitem__(self, index):
        sample = self.samples[index]
        return (
            (
                sample.image,
                sample.attribute_tensor,
                sample.locations,
                sample.masked_image,
            ),
            sample.target_pixels,
            sample.image_id,
        )

    def __len__(self) -> int:
        return len(self.samples)


@dataclass
class CaptionGeneratorSample:
    image_id: str
    image: torch.Tensor

    # target
    caption: torch.Tensor

    # additional attributes
    masked_image: torch.Tensor = torch.tensor(0)
    non_target_captions: torch.Tensor = torch.tensor(0)


class CaptionGeneratorDataset(Dataset):
    """
    Input:
     - image

    Ouput:
     - caption in form of (size, color, shape) e.g. large green sphere
    """

    def __init__(
        self,
        scenes_json_dir,
        image_loader: ImageLoader,
        max_number_samples,
        captioner: Captioner,
        image_masker: ImageMasker = None,
        preprocess=ResNet101_Weights.DEFAULT.transforms(),
    ) -> None:
        super().__init__()
        self.captioner = captioner
        self.samples: list[CaptionGeneratorSample] = []

        scenes = os.listdir(scenes_json_dir)
        print("sampling scenes...")
        selected_scenes = random.sample(scenes, max_number_samples)

        max_number_of_distractors = 0
        for scene_index, scene_file in enumerate(selected_scenes):
            if scene_index % 50 == 0:
                print(f"processing scene {scene_index}...", end="\r")

            with open(
                os.path.join(scenes_json_dir, scene_file), "r", encoding="utf-8"
            ) as f:
                scene = json.load(f)

            image_id = scene_file.removesuffix(".json")
            image, processed_image, _ = image_loader.get_image(image_id)

            target_object = scene["groups"]["target"][0]

            number_of_objects = len(scene["objects"])
            max_number_of_distractors = max(
                number_of_objects - 1, max_number_of_distractors
            )
            captions = []
            for obj_index in range(number_of_objects):
                captions.append(captioner.caption(scene, obj_index))

            target_caption = captions.pop(target_object)

            sample = CaptionGeneratorSample(
                image_id=image_id,
                image=processed_image,
                caption=target_caption,
                non_target_captions=torch.stack(captions),
            )

            if image_masker is not None:
                sample.masked_image = preprocess(
                    image_masker.get_masked_image(image, scene, target_object)
                )

            self.samples.append(sample)

        # pad non-target captions
        for sample in self.samples:
            padding = [torch.zeros_like(sample.non_target_captions[0])] * (
                max_number_of_distractors - len(sample.non_target_captions)
            )
            if len(padding) > 0:
                sample.non_target_captions = torch.cat(
                    (
                        sample.non_target_captions,
                        torch.stack(padding),
                    )
                )

        print()
        print("loaded data.")

    def __getitem__(self, index):
        sample = self.samples[index]
        return (
            (
                sample.image,
                sample.caption,
                sample.non_target_captions[:, 1:],
                sample.masked_image,
            ),
            sample.caption[1:],
            sample.image_id,
        )

    def __len__(self) -> int:
        return len(self.samples)