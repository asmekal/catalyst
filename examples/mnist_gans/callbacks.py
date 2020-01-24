"""
All custom callbacks
"""
from typing import Any, Callable, Dict, List, Optional, Union

import torch
import torchvision.utils

from catalyst.dl import RunnerState
from catalyst.dl.callbacks import CriterionCallback, OptimizerCallback
from catalyst.dl.core import Callback, CallbackOrder
from catalyst.utils.tensorboard import SummaryWriter


"""
MetricCallbacks alternatives for input/output keys
"""


class MultiKeyMetricCallback(Callback):
    """
    A callback that returns single metric on `state.on_batch_end`
    """

    # TODO:
    #  merge it with MetricCallback in catalyst.core
    #  maybe after the changes with CriterionCallback will be finalized
    #  in the main repo
    def __init__(
        self,
        prefix: str,
        metric_fn: Callable,
        input_key: Optional[Union[str, List[str]]] = "targets",
        output_key: Optional[Union[str, List[str]]] = "logits",
        **metric_params
    ):
        super().__init__(CallbackOrder.Metric)
        self.prefix = prefix
        self.metric_fn = metric_fn
        self.input_key = input_key
        self.output_key = output_key
        self.metric_params = metric_params

    @staticmethod
    def _get(dictionary: dict, keys: Optional[Union[str, List[str]]]) -> Any:
        if keys is None:
            result = dictionary
        elif isinstance(keys, list):
            result = {key: dictionary[key] for key in keys}
        else:
            result = dictionary[keys]
        return result

    def on_batch_end(self, state: RunnerState):
        outputs = self._get(state.output, self.output_key)
        targets = self._get(state.input, self.input_key)
        metric = self.metric_fn(outputs, targets, **self.metric_params)
        state.metrics.add_batch_value(name=self.prefix, value=metric)


class WassersteinDistanceCallback(MultiKeyMetricCallback):
    def __init__(
        self,
        prefix: str = "wasserstein_distance",
        real_validity_output_key: str = "real_validity",
        fake_validity_output_key: str = "fake_validity"
    ):
        super().__init__(
            prefix,
            metric_fn=self.get_wasserstein_distance,
            input_key=None,
            output_key=[real_validity_output_key, fake_validity_output_key]
        )
        self.real_validity_key = real_validity_output_key
        self.fake_validity_key = fake_validity_output_key

    def get_wasserstein_distance(self, outputs, targets):
        real_validity = outputs[self.real_validity_key]
        fake_validity = outputs[self.fake_validity_key]
        return real_validity.mean() - fake_validity.mean()


"""
CriterionCallback extended
"""


class CriterionWithDiscriminatorCallback(CriterionCallback):
    """Callback to handle Criterion which has additional argument (model)
    as input.
    So imagine you have CRITERION with
        forward(self, outputs, inputs, discriminator)
    This callback will add discriminator to criterion forward arguments
    """
    def __init__(
        self,
        input_key: Union[str, List[str]] = "targets",
        output_key: Union[str, List[str]] = "logits",
        prefix: str = "loss",
        criterion_key: str = None,
        multiplier: float = 1.0,
        discriminator_model_key="discriminator",
        discriminator_model_criterion_key="discriminator"
    ):
        """

        :param input_key:
        :param output_key:
        :param prefix:
        :param criterion_key:
        :param multiplier:
        :param discriminator_model_key:
            discriminator key to extract from state.model
        :param discriminator_model_criterion_key:
            discriminator key in criterion forward
            Example 1:
                forward(self, outputs, inputs, discriminator)
                (here discriminator_model_criterion_key is "discriminator")
            Example 2:
                forward(self, outputs, inputs, d_model)
                (here discriminator_model_criterion_key is "d_model")
        """
        super().__init__(
            input_key, output_key, prefix, criterion_key, multiplier
        )
        self.discriminator_model_key = \
            discriminator_model_key
        self.discriminator_model_criterion_key = \
            discriminator_model_criterion_key

    def _get_additional_criterion_args(self, state: RunnerState):
        return {
            self.discriminator_model_criterion_key: state.model[
                self.discriminator_model_key]
        }


"""
Optimizer Callback with weights clamp after update
"""


class WeightClampingOptimizerCallback(OptimizerCallback):
    """
    Optimizer callback + weights clipping after step is finished
    """
    def __init__(
        self,
        grad_clip_params: Dict = None,
        accumulation_steps: int = 1,
        optimizer_key: str = None,
        loss_key: str = "loss",
        decouple_weight_decay: bool = True,
        weight_clamp_value: float = 0.1
    ):
        """

        :param grad_clip_params:
        :param accumulation_steps:
        :param optimizer_key:
        :param loss_key:
        :param decouple_weight_decay:
        :param weight_clamp_value:
            value to clamp weights after each optimization iteration
            Attention: will clamp WEIGHTS, not GRADIENTS
        """
        super().__init__(
            grad_clip_params=grad_clip_params,
            accumulation_steps=accumulation_steps,
            optimizer_key=optimizer_key,
            loss_key=loss_key,
            decouple_weight_decay=decouple_weight_decay
        )
        self.weight_clamp_value = weight_clamp_value

    def on_batch_end(self, state):
        """On batch end event"""
        super().on_batch_end(state)
        if not state.need_backward:
            return

        optimizer = state.get_key(
            key="optimizer", inner_key=self.optimizer_key
        )

        need_gradient_step = \
            self._accumulation_counter % self.accumulation_steps == 0

        if need_gradient_step:
            for group in optimizer.param_groups:
                for param in group["params"]:
                    param.data.clamp_(
                        min=-self.weight_clamp_value,
                        max=self.weight_clamp_value
                    )


"""
Visualization utilities
"""


class VisualizationCallback(Callback):
    TENSORBOARD_LOGGER_KEY = "tensorboard"

    def __init__(
        self,
        input_keys=None,
        output_keys=None,
        batch_frequency=25,
        concat_images=True,
        max_images=20,
        n_row=1,
        denorm="default"
    ):
        super().__init__(CallbackOrder.Other)
        if input_keys is None:
            self.input_keys = []
        elif isinstance(input_keys, str):
            self.input_keys = [input_keys]
        elif isinstance(input_keys, (tuple, list)):
            assert all(isinstance(k, str) for k in input_keys)
            self.input_keys = list(input_keys)
        else:
            raise ValueError(
                f"Unexpected format of 'input_keys' "
                f"argument: must be string or list/tuple"
            )

        if output_keys is None:
            self.output_keys = []
        elif isinstance(output_keys, str):
            self.output_keys = [output_keys]
        elif isinstance(output_keys, (tuple, list)):
            assert all(isinstance(k, str) for k in output_keys)
            self.output_keys = list(output_keys)
        else:
            raise ValueError(
                f"Unexpected format of 'output_keys' "
                f"argument: must be string or list/tuple"
            )

        if len(self.input_keys) + len(self.output_keys) == 0:
            raise ValueError("Useless visualizer: pass at least one image key")

        self.batch_frequency = int(batch_frequency)
        assert self.batch_frequency > 0

        self.concat_images = concat_images
        self.max_images = max_images
        if denorm.lower() == "default":
            # normalization from [-1, 1] to [0, 1] (the latter is valid for tb)
            self.denorm = lambda x: x / 2 + .5
        elif denorm is None or denorm.lower() == "none":
            self.denorm = lambda x: x
        else:
            raise ValueError("unknown denorm fn")
        self._n_row = n_row
        self._reset()

    def _reset(self):
        self._loader_batch_count = 0
        self._loader_visualized_in_current_epoch = False

    @staticmethod
    def _get_tensorboard_logger(state: RunnerState) -> SummaryWriter:
        tb_key = VisualizationCallback.TENSORBOARD_LOGGER_KEY
        if (
            tb_key in state.loggers
            and state.loader_name in state.loggers[tb_key].loggers
        ):
            return state.loggers[tb_key].loggers[state.loader_name]
        raise RuntimeError(
            f"Cannot find Tensorboard logger for loader {state.loader_name}"
        )

    def compute_visualizations(self, state):
        input_tensors = [
            state.input[input_key] for input_key in self.input_keys
        ]
        output_tensors = [
            state.output[output_key] for output_key in self.output_keys
        ]
        visualizations = dict()
        if self.concat_images:
            viz_name = "|".join(self.input_keys + self.output_keys)
            viz_tensor = self.denorm(
                # concat by width
                torch.cat(input_tensors + output_tensors, dim=3)
            ).detach().cpu()
            visualizations[viz_name] = viz_tensor
        else:
            visualizations = dict(
                (k, self.denorm(v)) for k, v in zip(
                    self.input_keys + self.output_keys, input_tensors +
                    output_tensors
                )
            )
        return visualizations

    def save_visualizations(self, state, visualizations):
        tb_logger = self._get_tensorboard_logger(state)
        for key, batch_images in visualizations.items():
            batch_images = batch_images[:self.max_images]
            image = torchvision.utils.make_grid(batch_images, nrow=self._n_row)
            tb_logger.add_image(key, image, global_step=state.step)

    def visualize(self, state):
        visualizations = self.compute_visualizations(state)
        self.save_visualizations(state, visualizations)
        self._loader_visualized_in_current_epoch = True

    def on_loader_start(self, state: RunnerState):
        self._reset()

    def on_loader_end(self, state: RunnerState):
        if not self._loader_visualized_in_current_epoch:
            self.visualize(state)

    def on_batch_end(self, state: RunnerState):
        self._loader_batch_count += 1
        if self._loader_batch_count % self.batch_frequency:
            self.visualize(state)


__all__ = [
    "MultiKeyMetricCallback",
    "WassersteinDistanceCallback", "CriterionWithDiscriminatorCallback",
    "WeightClampingOptimizerCallback", "VisualizationCallback"
]