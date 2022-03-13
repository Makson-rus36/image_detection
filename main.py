labels = ["person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck",
          "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
          "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
          "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
          "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
          "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana",
          "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
          "chair", "sofa", "pottedplant", "bed", "diningtable", "toilet", "tvmonitor", "laptop", "mouse",
          "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
          "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"]

import argparse
import numpy as np
import struct

from matplotlib.patches import Rectangle
from numpy import expand_dims
from keras.layers import Input, Conv2D, BatchNormalization, LeakyReLU, ZeroPadding2D, UpSampling2D
from keras.models import load_model, Model
from keras.layers.merge import add, concatenate
from keras.preprocessing.image import load_img
from keras.preprocessing.image import img_to_array
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument('--image_path', help="Path of image to detect objects", default="images/road-1.jpg")
parser.add_argument('--create_model', help="Create, train and save model. 0 - Skip; 1 - Enable", default=0)
parser.add_argument('--threshold', help="Min threshold for detect object. Default: 0.4; Min: 0.1; Max: 1.0",
                    default=0.98)
parser.add_argument('--detection', help="Use for detection type object. Default: all", default="all")
args = parser.parse_args()


class WeightReader:
    def __init__(self, weight_file):
        with open(weight_file, 'rb') as w_f:
            major, = struct.unpack('i', w_f.read(4))
            minor, = struct.unpack('i', w_f.read(4))
            revision, = struct.unpack('i', w_f.read(4))
            if (major * 10 + minor) >= 2 and major < 1000 and minor < 1000:
                w_f.read(8)
            else:
                w_f.read(4)
            transpose = (major > 1000) or (minor > 1000)
            binary = w_f.read()
        self.offset = 0
        self.all_weights = np.frombuffer(binary, dtype='float32')

    def read_bytes(self, size):
        self.offset = self.offset + size
        return self.all_weights[self.offset - size:self.offset]

    def load_weights(self, model):
        for i in range(106):
            try:
                conv_layer = model.get_layer('conv_' + str(i))
                print("loading weights of convolution #" + str(i))
                if i not in [81, 93, 105]:
                    norm_layer = model.get_layer('bnorm_' + str(i))
                    size = np.prod(norm_layer.get_weights()[0].shape)
                    beta = self.read_bytes(size)  # bias
                    gamma = self.read_bytes(size)  # scale
                    mean = self.read_bytes(size)  # mean
                    var = self.read_bytes(size)  # variance
                    weights = norm_layer.set_weights([gamma, beta, mean, var])
                if len(conv_layer.get_weights()) > 1:
                    bias = self.read_bytes(np.prod(conv_layer.get_weights()[1].shape))
                    kernel = self.read_bytes(np.prod(conv_layer.get_weights()[0].shape))
                    kernel = kernel.reshape(list(reversed(conv_layer.get_weights()[0].shape)))
                    kernel = kernel.transpose([2, 3, 1, 0])
                    conv_layer.set_weights([kernel, bias])
                else:
                    kernel = self.read_bytes(np.prod(conv_layer.get_weights()[0].shape))
                    kernel = kernel.reshape(list(reversed(conv_layer.get_weights()[0].shape)))
                    kernel = kernel.transpose([2, 3, 1, 0])
                    conv_layer.set_weights([kernel])
            except ValueError:
                print("no convolution #" + str(i))

    def reset(self):
        self.offset = 0


class CreateModel:
    def __init__(self):
        print("START INIT")
        self.make_yolov3_model()

    def _conv_block(self, inp, convs, skip=True):
        x = inp
        count = 0
        for conv in convs:
            if count == (len(convs) - 2) and skip:
                skip_connection = x
            count += 1
            if conv['stride'] > 1: x = ZeroPadding2D(((1, 0), (1, 0)))(
                x)
            x = Conv2D(conv['filter'],
                       conv['kernel'],
                       strides=conv['stride'],
                       padding='valid' if conv['stride'] > 1 else 'same',
                       name='conv_' + str(conv['layer_idx']),
                       use_bias=False if conv['bnorm'] else True)(x)
            if conv['bnorm']: x = BatchNormalization(epsilon=0.001, name='bnorm_' + str(conv['layer_idx']))(x)
            if conv['leaky']: x = LeakyReLU(alpha=0.1, name='leaky_' + str(conv['layer_idx']))(x)
        return add([skip_connection, x]) if skip else x

    def make_yolov3_model(self):
        input_image = Input(shape=(None, None, 3))
        # Layer  0 => 4
        x = self._conv_block(input_image,
                             [{'filter': 32, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 0},
                              {'filter': 64, 'kernel': 3, 'stride': 2, 'bnorm': True, 'leaky': True, 'layer_idx': 1},
                              {'filter': 32, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 2},
                              {'filter': 64, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 3}])
        # Layer  5 => 8
        x = self._conv_block(x,
                             [{'filter': 128, 'kernel': 3, 'stride': 2, 'bnorm': True, 'leaky': True, 'layer_idx': 5},
                              {'filter': 64, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 6},
                              {'filter': 128, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 7}])
        # Layer  9 => 11
        x = self._conv_block(x, [{'filter': 64, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 9},
                                 {'filter': 128, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True,
                                  'layer_idx': 10}])
        # Layer 12 => 15
        x = self._conv_block(x,
                             [{'filter': 256, 'kernel': 3, 'stride': 2, 'bnorm': True, 'leaky': True, 'layer_idx': 12},
                              {'filter': 128, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 13},
                              {'filter': 256, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 14}])
        # Layer 16 => 36
        for i in range(7):
            x = self._conv_block(x, [
                {'filter': 128, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 16 + i * 3},
                {'filter': 256, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 17 + i * 3}])
        skip_36 = x
        # Layer 37 => 40
        x = self._conv_block(x,
                             [{'filter': 512, 'kernel': 3, 'stride': 2, 'bnorm': True, 'leaky': True, 'layer_idx': 37},
                              {'filter': 256, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 38},
                              {'filter': 512, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 39}])
        # Layer 41 => 61
        for i in range(7):
            x = self._conv_block(x, [
                {'filter': 256, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 41 + i * 3},
                {'filter': 512, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 42 + i * 3}])
        skip_61 = x
        # Layer 62 => 65
        x = self._conv_block(x,
                             [{'filter': 1024, 'kernel': 3, 'stride': 2, 'bnorm': True, 'leaky': True, 'layer_idx': 62},
                              {'filter': 512, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 63},
                              {'filter': 1024, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True,
                               'layer_idx': 64}])
        # Layer 66 => 74
        for i in range(3):
            x = self._conv_block(x, [
                {'filter': 512, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 66 + i * 3},
                {'filter': 1024, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 67 + i * 3}])
        # Layer 75 => 79
        x = self._conv_block(x,
                             [{'filter': 512, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 75},
                              {'filter': 1024, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 76},
                              {'filter': 512, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 77},
                              {'filter': 1024, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 78},
                              {'filter': 512, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 79}],
                             skip=False)
        # Layer 80 => 82
        yolo_82 = self._conv_block(x, [
            {'filter': 1024, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 80},
            {'filter': 255, 'kernel': 1, 'stride': 1, 'bnorm': False, 'leaky': False,
             'layer_idx': 81}], skip=False)
        # Layer 83 => 86
        x = self._conv_block(x,
                             [{'filter': 256, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 84}],
                             skip=False)
        x = UpSampling2D(2)(x)
        x = concatenate([x, skip_61])
        # Layer 87 => 91
        x = self._conv_block(x,
                             [{'filter': 256, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 87},
                              {'filter': 512, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 88},
                              {'filter': 256, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 89},
                              {'filter': 512, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 90},
                              {'filter': 256, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 91}],
                             skip=False)
        # Layer 92 => 94
        yolo_94 = self._conv_block(x,
                                   [{'filter': 512, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True,
                                     'layer_idx': 92},
                                    {'filter': 255, 'kernel': 1, 'stride': 1, 'bnorm': False, 'leaky': False,
                                     'layer_idx': 93}], skip=False)
        # Layer 95 => 98
        x = self._conv_block(x,
                             [{'filter': 128, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 96}],
                             skip=False)
        x = UpSampling2D(2)(x)
        x = concatenate([x, skip_36])
        # Layer 99 => 106
        yolo_106 = self._conv_block(x, [
            {'filter': 128, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True, 'layer_idx': 99},
            {'filter': 256, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True,
             'layer_idx': 100},
            {'filter': 128, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True,
             'layer_idx': 101},
            {'filter': 256, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True,
             'layer_idx': 102},
            {'filter': 128, 'kernel': 1, 'stride': 1, 'bnorm': True, 'leaky': True,
             'layer_idx': 103},
            {'filter': 256, 'kernel': 3, 'stride': 1, 'bnorm': True, 'leaky': True,
             'layer_idx': 104},
            {'filter': 255, 'kernel': 1, 'stride': 1, 'bnorm': False, 'leaky': False,
             'layer_idx': 105}], skip=False)
        model = Model(input_image, [yolo_82, yolo_94, yolo_106])
        print("INIT DONE")
        print("LOAD WEIGHT START")
        self.load_weights_and_save(model)

    # define the model

    def load_weights_and_save(self, model):
        weight_reader = WeightReader('yolov3.weights')
        weight_reader.load_weights(model)
        model.save('model.h5')
        model_json = model.to_json()
        with open('model.json', "w") as json_file:
            json_file.write(model_json)
        print("LOAD WEIGHT END.")
        print("SAVE MODEL: OK.")


class BoundBox:
    def __init__(self, xmin, ymin, xmax, ymax, objness=None, classes=None):
        self.xmin = xmin
        self.ymin = ymin
        self.xmax = xmax
        self.ymax = ymax

        self.objness = objness
        self.classes = classes

        self.label = -1
        self.score = -1

    def get_label(self):
        if self.label == -1:
            self.label = np.argmax(self.classes)

        return self.label

    def get_score(self):
        if self.score == -1:
            self.score = self.classes[self.get_label()]

        return self.score


class DetectObject:
    def _sigmoid(self, x):
        return 1. / (1. + np.exp(-x))

    def _interval_overlap(self, interval_a, interval_b):
        x1, x2 = interval_a
        x3, x4 = interval_b

        if x3 < x1:
            if x4 < x1:
                return 0
            else:
                return min(x2, x4) - x1
        else:
            if x2 < x3:
                return 0
            else:
                return min(x2, x4) - x3

    def bbox_iou(self, box1, box2):
        intersect_w = self._interval_overlap([box1.xmin, box1.xmax], [box2.xmin, box2.xmax])
        intersect_h = self._interval_overlap([box1.ymin, box1.ymax], [box2.ymin, box2.ymax])
        intersect = intersect_w * intersect_h
        w1, h1 = box1.xmax - box1.xmin, box1.ymax - box1.ymin
        w2, h2 = box2.xmax - box2.xmin, box2.ymax - box2.ymin
        union = w1 * h1 + w2 * h2 - intersect
        return float(intersect) / union

    def do_nms(self, boxes, nms_thresh):
        if len(boxes) > 0:
            nb_class = len(boxes[0].classes)
        else:
            return

        for c in range(nb_class):
            sorted_indices = np.argsort([-box.classes[c] for box in boxes])
            for i in range(len(sorted_indices)):
                index_i = sorted_indices[i]
                if boxes[index_i].classes[c] == 0: continue
                for j in range(i + 1, len(sorted_indices)):
                    index_j = sorted_indices[j]

                    if self.bbox_iou(boxes[index_i], boxes[index_j]) >= nms_thresh:
                        boxes[index_j].classes[c] = 0

    def decode_netout(self, netout, anchors, obj_thresh, net_h, net_w):
        grid_h, grid_w = netout.shape[:2]
        nb_box = 3
        netout = netout.reshape((grid_h, grid_w, nb_box, -1))
        nb_class = netout.shape[-1] - 5

        boxes = []

        netout[..., :2] = self._sigmoid(netout[..., :2])
        netout[..., 4:] = self._sigmoid(netout[..., 4:])
        netout[..., 5:] = netout[..., 4][..., np.newaxis] * netout[..., 5:]
        netout[..., 5:] *= netout[..., 5:] > obj_thresh

        for i in range(grid_h * grid_w):
            row = i / grid_w
            col = i % grid_w

            for b in range(nb_box):
                objectness = netout[int(row)][int(col)][b][4]
                if (objectness.all() <= obj_thresh): continue
                x, y, w, h = netout[int(row)][int(col)][b][:4]
                x = (col + x) / grid_w
                y = (row + y) / grid_h
                w = anchors[2 * b + 0] * np.exp(w) / net_w
                h = anchors[2 * b + 1] * np.exp(h) / net_h
                classes = netout[int(row)][col][b][5:]
                box = BoundBox(x - w / 2, y - h / 2, x + w / 2, y + h / 2, objectness, classes)
                boxes.append(box)

        return boxes

    def correct_yolo_boxes(self, boxes, image_h, image_w, net_h, net_w):
        if (float(net_w) / image_w) > (float(net_h) / image_h):
            new_w = net_w
            new_h = (image_h * net_w) / image_w
        else:
            new_h = net_w
            new_w = (image_w * net_h) / image_h

        for i in range(len(boxes)):
            x_offset, x_scale = (net_w - new_w) / 2. / net_w, float(new_w) / net_w
            y_offset, y_scale = (net_h - new_h) / 2. / net_h, float(new_h) / net_h

            boxes[i].xmin = int((boxes[i].xmin - x_offset) / x_scale * image_w)
            boxes[i].xmax = int((boxes[i].xmax - x_offset) / x_scale * image_w)
            boxes[i].ymin = int((boxes[i].ymin - y_offset) / y_scale * image_h)
            boxes[i].ymax = int((boxes[i].ymax - y_offset) / y_scale * image_h)

    def draw_boxes(self, filename, v_boxes, v_labels, v_scores, detection: str = 'all'):
        data = plt.imread(filename)
        plt.imshow(data)
        ax = plt.gca()
        for i in range(len(v_boxes)):
            box = v_boxes[i]
            y1, x1, y2, x2 = box.ymin, box.xmin, box.ymax, box.xmax
            width, height = x2 - x1, y2 - y1
            if detection == 'all':
                if v_labels[i] == 'bus' \
                        or v_labels[i] == 'car' \
                        or v_labels[i] == 'truck' \
                        or v_labels[i] == 'motorbike':
                    rect = Rectangle((x1, y1), width, height, fill=False, color='red')
                    ax.add_patch(rect)
                    label = "%s (%.3f)" % (v_labels[i], v_scores[i])
                    plt.text(x1, y1, label, color='red')
            else:
                if detection == v_labels[i]:
                    rect = Rectangle((x1, y1), width, height, fill=False, color='red')
                    ax.add_patch(rect)
                    label = "%s (%.3f)" % (v_labels[i], v_scores[i])
                    plt.text(x1, y1, label, color='red')

        plt.savefig('result.png')
        return True

    def get_boxes(self, boxes, labels, thresh):
        v_boxes, v_labels, v_scores = list(), list(), list()
        for box in boxes:
            for i in range(len(labels)):
                if box.classes[i] > thresh:
                    v_boxes.append(box)
                    v_labels.append(labels[i])
                    v_scores.append(box.classes[i] * 100)
        return v_boxes, v_labels, v_scores


class LoadImage:

    def load_image_pixels(self, filename, shape):
        image = load_img(filename)
        width, height = image.size
        image = load_img(filename, target_size=shape)
        image = img_to_array(image)
        image = image.astype('float32')
        image /= 255.0
        image = expand_dims(image, 0)
        return image, width, height


net_h, net_w = 416, 416
obj_thresh, nms_thresh = 0.5, 0.45
anchors = [[116, 90, 156, 198, 373, 326], [30, 61, 62, 45, 59, 119], [10, 13, 16, 30, 33, 23]]


def start_main(create_model: int = 0, image_path: str="example.jpg", threshold: float = 1.0, detection_class: str = 'all'):
    if create_model == 1:
        cm = CreateModel()
    yolov3 = load_model('model.h5')
    input_w, input_h = 416, 416
    photo_filename = image_path
    li = LoadImage()
    image, image_w, image_h = li.load_image_pixels(photo_filename, (input_w, input_h))
    yolos = yolov3.predict(image)
    class_threshold = threshold
    boxes = list()
    dt = DetectObject()
    for i in range(len(yolos)):
        boxes += dt.decode_netout(yolos[i][0], anchors[i], obj_thresh, net_h, net_w)

    dt.correct_yolo_boxes(boxes, image_h, image_w, net_h, net_w)
    dt.do_nms(boxes, nms_thresh)
    v_boxes, v_labels, v_scores = dt.get_boxes(boxes, labels, class_threshold)
    return dt.draw_boxes(photo_filename, v_boxes, v_labels, v_scores, detection_class)


if __name__ == "__main__":
    start_main(0, "images/road-1.jpg" )
