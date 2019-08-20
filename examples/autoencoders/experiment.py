from collections import OrderedDict
import torchvision
from torchvision import transforms
from catalyst.dl import ConfigExperiment

from torch.utils.data import Dataset as TorchDataset
import numpy as np


class YAEDataset(TorchDataset):
    def __init__(self, inner_dataset, n_classes=10):
        super().__init__()
        self.inner_dataset = inner_dataset
        self.n_classses = n_classes

    def __getitem__(self, item):
        image, target = self.inner_dataset[item]
        target2 = np.random.randint(self.n_classses)
        return image, target, target2

    def __len__(self):
        return len(self.inner_dataset)


class Experiment(ConfigExperiment):
    @staticmethod
    def get_transforms(stage: str = None, mode: str = None):
        return transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
            ]
        )

    def get_datasets(self, stage: str, **kwargs):
        datasets = OrderedDict()

        trainset = torchvision.datasets.CIFAR10(
            root="./data",
            train=True,
            download=True,
            transform=Experiment.get_transforms(stage=stage, mode="train")
        )
        testset = torchvision.datasets.CIFAR10(
            root="./data",
            train=False,
            download=True,
            transform=Experiment.get_transforms(stage=stage, mode="valid")
        )

        datasets["train"] = YAEDataset(trainset)
        datasets["valid"] = YAEDataset(testset)

        return datasets
