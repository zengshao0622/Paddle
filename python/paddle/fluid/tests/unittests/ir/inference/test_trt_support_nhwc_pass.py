# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import shutil
import unittest

import numpy as np

import paddle
import paddle.inference as inference
import paddle.nn as nn
import paddle.static as static

paddle.enable_static()


class SimpleNet(nn.Layer):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2D(
            in_channels=4,
            out_channels=4,
            kernel_size=3,
            stride=2,
            padding=0,
            data_format='NHWC',
        )
        self.relu1 = nn.ReLU()
        self.conv2 = nn.Conv2D(
            in_channels=4,
            out_channels=2,
            kernel_size=3,
            stride=2,
            padding=0,
            data_format='NHWC',
        )
        self.relu2 = nn.ReLU()
        self.conv3 = nn.Conv2D(
            in_channels=2,
            out_channels=1,
            kernel_size=3,
            stride=2,
            padding=0,
            data_format='NHWC',
        )
        self.relu3 = nn.ReLU()
        self.flatten = nn.Flatten()
        self.fc = nn.Linear(729, 10)
        self.softmax = nn.Softmax()

    def forward(self, x):
        x = self.conv1(x)
        x = self.relu1(x)
        x = self.conv2(x)
        x = self.relu2(x)
        x = self.conv3(x)
        x = self.relu3(x)
        x = self.flatten(x)
        x = self.fc(x)
        x = self.softmax(x)
        return x


class TRTNHWCConvertTest(unittest.TestCase):
    def setUp(self):
        self.place = paddle.CUDAPlace(0)
        self.path = './inference_pass/nhwc_convert/infer_model'

    def create_model(self):
        image = static.data(
            name='img', shape=[None, 224, 224, 4], dtype='float32'
        )
        predict = SimpleNet()(image)
        exe = paddle.static.Executor(self.place)
        exe.run(paddle.static.default_startup_program())
        paddle.static.save_inference_model(self.path, [image], [predict], exe)

    def create_predictor(self):
        config = paddle.inference.Config(
            self.path + '.pdmodel', self.path + '.pdiparams'
        )
        config.enable_memory_optim()
        config.enable_use_gpu(100, 0)
        config.enable_tensorrt_engine(
            workspace_size=1 << 30,
            max_batch_size=1,
            min_subgraph_size=3,
            precision_mode=inference.PrecisionType.Float32,
            use_static=False,
            use_calib_mode=False,
        )
        predictor = inference.create_predictor(config)
        return predictor

    def infer(self, predictor, img):
        input_names = predictor.get_input_names()
        for i, name in enumerate(input_names):
            input_tensor = predictor.get_input_handle(name)
            input_tensor.reshape(img[i].shape)
            input_tensor.copy_from_cpu(img[i].copy())
        predictor.run()
        results = []
        output_names = predictor.get_output_names()
        for i, name in enumerate(output_names):
            output_tensor = predictor.get_output_handle(name)
            output_data = output_tensor.copy_to_cpu()
            results.append(output_data)
        return results

    def test_nhwc_convert(self):
        self.create_model()
        predictor = self.create_predictor()
        img = np.ones((1, 224, 224, 4), dtype=np.float32)
        result = self.infer(predictor, img=[img])

    def tearDown(self):
        shutil.rmtree('./inference_pass/nhwc_convert/')


if __name__ == '__main__':
    unittest.main()
