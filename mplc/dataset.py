# -*- coding: utf-8 -*-
"""
The dataset object used in the multi-partner learning and contributivity measurement experiments.
"""
import glob
import shutil
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import urlretrieve

import numpy as np
import pandas as pd
from joblib import dump, load
from keras.datasets import cifar10, mnist, imdb
from keras.layers import Activation
from keras.layers import Conv2D, GlobalAveragePooling2D, MaxPooling2D
from keras.layers import Dense, Dropout
from keras.layers import Embedding, Conv1D, MaxPooling1D, Flatten
from keras.losses import categorical_crossentropy
from keras.models import Sequential
from keras.optimizers import RMSprop
from keras.preprocessing import sequence
from keras.utils import to_categorical
from librosa import load as wav_load
from librosa.feature import mfcc
from loguru import logger
from sklearn.linear_model import LogisticRegression as skLR
from sklearn.metrics import log_loss
from sklearn.model_selection import train_test_split

from . import constants


class Dataset(ABC):

    def __init__(self,
                 dataset_name,
                 input_shape,
                 num_classes,
                 x_train,
                 y_train,
                 x_test,
                 y_test
                 ):
        self.name = dataset_name

        self.input_shape = input_shape
        self.num_classes = num_classes

        self.x_train = x_train
        self.x_val = None
        self.x_test = x_test
        self.y_train = y_train
        self.y_val = None
        self.y_test = y_test

        self.train_val_split_global()

    def train_val_split_global(self):
        """Called once, at the end of Dataset's constructor"""
        if self.x_val or self.y_val:
            raise Exception("x_val and y_val should be of NoneType")
        self.x_train, self.x_val, self.y_train, self.y_val = train_test_split(self.x_train,
                                                                              self.y_train,
                                                                              test_size=0.1,
                                                                              random_state=42)

    @staticmethod
    def train_test_split_local(x, y):
        return x, np.array([]), y, np.array([])

    @staticmethod
    def train_val_split_local(x, y):
        return x, np.array([]), y, np.array([])

    @abstractmethod
    def generate_new_model(self):
        pass

    def shorten_dataset_proportion(self, dataset_proportion):
        """Truncate the dataset depending on self.dataset_proportion"""

        if dataset_proportion == 1:
            return
        elif dataset_proportion < 0:
            raise ValueError("The dataset proportion should be strictly between 0 and 1")
        else:
            logger.info(f"We don't use the full dataset: only {dataset_proportion * 100}%")

            skip_train_idx = int(round(len(self.x_train) * dataset_proportion))
            train_idx = np.arange(len(self.x_train))

            skip_val_idx = int(round(len(self.x_val) * dataset_proportion))
            val_idx = np.arange(len(self.x_val))

            np.random.seed(42)
            np.random.shuffle(train_idx)
            np.random.shuffle(val_idx)

            self.x_train = self.x_train[train_idx[0:skip_train_idx]]
            self.y_train = self.y_train[train_idx[0:skip_train_idx]]
            self.x_val = self.x_val[val_idx[0:skip_val_idx]]
            self.y_val = self.y_val[val_idx[0:skip_val_idx]]


class Cifar10(Dataset):
    def __init__(self):
        self.input_shape = (32, 32, 3)
        self.num_classes = 10
        x_test, x_train, y_test, y_train = self.load_data()

        super(Cifar10, self).__init__(dataset_name='cifar10',
                                      num_classes=self.num_classes,
                                      input_shape=self.input_shape,
                                      x_train=x_train,
                                      y_train=y_train,
                                      x_test=x_test,
                                      y_test=y_test)

    def load_data(self):
        attempts = 0
        while True:
            try:
                (x_train, y_train), (x_test, y_test) = cifar10.load_data()
                break
            except (HTTPError, URLError) as e:
                if hasattr(e, 'code'):
                    temp = e.code
                else:
                    temp = e.errno
                logger.debug(
                    f'URL fetch failure on '
                    f'https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz : '
                    f'{temp} -- {e.reason}')
                if attempts < constants.NUMBER_OF_DOWNLOAD_ATTEMPTS:
                    sleep(2)
                    attempts += 1
                else:
                    raise
        y_train = y_train.flatten()
        y_test = y_test.flatten()
        # Pre-process inputs
        x_train = self.preprocess_dataset_inputs(x_train)
        x_test = self.preprocess_dataset_inputs(x_test)
        y_train = self.preprocess_dataset_labels(y_train)
        y_test = self.preprocess_dataset_labels(y_test)
        return x_test, x_train, y_test, y_train

    # Data samples pre-processing method for inputs
    @staticmethod
    def preprocess_dataset_inputs(x):
        x = x.astype("float32")
        x /= 255

        return x

    # Data samples pre-processing method for labels
    def preprocess_dataset_labels(self, y):
        y = to_categorical(y, self.num_classes)

        return y

    # Model structure and generation
    def generate_new_model(self):
        """Return a CNN model from scratch based on given batch_size"""

        model = Sequential()
        model.add(Conv2D(32, (3, 3), padding='same', input_shape=self.input_shape))
        model.add(Activation('relu'))
        model.add(Conv2D(32, (3, 3)))
        model.add(Activation('relu'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Dropout(0.25))

        model.add(Conv2D(64, (3, 3), padding='same'))
        model.add(Activation('relu'))
        model.add(Conv2D(64, (3, 3)))
        model.add(Activation('relu'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Dropout(0.25))

        model.add(Flatten())
        model.add(Dense(512))
        model.add(Activation('relu'))
        model.add(Dropout(0.5))
        model.add(Dense(self.num_classes))
        model.add(Activation('softmax'))

        # initiate RMSprop optimizer
        opt = RMSprop(learning_rate=0.0001, decay=1e-6)

        # Let's train the model using RMSprop
        model.compile(loss='categorical_crossentropy',
                      optimizer=opt,
                      metrics=['accuracy'])

        return model

    # train, test, val splits
    @staticmethod
    def train_test_split_local(x, y):
        return train_test_split(x, y, test_size=0.1, random_state=42)

    @staticmethod
    def train_val_split_local(x, y):
        return train_test_split(x, y, test_size=0.1, random_state=42)


class Titanic(Dataset):
    def __init__(self):
        self.num_classes = 2
        self.input_shape = (27,)
        # Load data
        (x_train, y_train), (x_test, y_test) = self.load_data()

        super(Titanic, self).__init__(dataset_name='titanic',
                                      num_classes=self.num_classes,
                                      input_shape=self.input_shape,
                                      x_train=x_train,
                                      y_train=y_train,
                                      x_test=x_test,
                                      y_test=y_test
                                      )

    # Init dataset-specific functions
    @staticmethod
    def preprocess_dataset_labels(y):
        """Legacy"""

        return y

    @staticmethod
    def preprocess_dataset_inputs(x):
        """Feature engineering"""

        x['Fam_size'] = x['Siblings/Spouses Aboard'] + x['Parents/Children Aboard']

        x['Name_Len'] = [len(i) for i in x["Name"]]

        x['Is_alone'] = [i == 0 for i in x["Fam_size"]]

        x["Sex"] = [i == "Male" for i in x["Sex"]]

        x['Title'] = [i.split()[0] for i in x["Name"]]
        x = pd.concat([x, pd.get_dummies(x['Title'])], axis=1)

        x = pd.concat([x, pd.get_dummies(x['Pclass'])], axis=1)

        # Dropping the useless features
        x.drop('Name', axis=1, inplace=True)
        x.drop('Pclass', axis=1, inplace=True)
        x.drop('Siblings/Spouses Aboard', axis=1, inplace=True)
        x.drop('Parents/Children Aboard', axis=1, inplace=True)
        x.drop('Title', axis=1, inplace=True)
        return x.to_numpy(dtype='float32')

    def load_data(self):
        """Return a usable dataset"""
        path = Path(__file__).resolve().parents[0]
        folder = path / 'local_data' / 'titanic'
        if not folder.is_dir():
            Path.mkdir(folder, parents=True)
            logger.info('Titanic dataset not found. Downloading it...')
            attempts = 0
            while True:
                try:
                    raw_dataset = pd.read_csv(
                        'https://web.stanford.edu/class/archive/cs/cs109/cs109.1166/stuff/titanic.csv',
                        index_col=False)
                    break
                except (HTTPError, URLError) as e:
                    if hasattr(e, 'code'):
                        temp = e.code
                    else:
                        temp = e.errno
                    logger.debug(
                        f'URL fetch failure on '
                        f'https://web.stanford.edu/class/archive/cs/cs109/cs109.1166/stuff/titanic.csv : '
                        f'{temp} -- {e.reason}')
                    if attempts < constants.NUMBER_OF_DOWNLOAD_ATTEMPTS:
                        sleep(2)
                        attempts += 1
                    else:
                        raise

            raw_dataset.to_csv((folder / "titanic.csv").resolve())
        else:
            raw_dataset = pd.read_csv((folder / "titanic.csv").resolve())
        x = raw_dataset.drop('Survived', axis=1)
        x = self.preprocess_dataset_inputs(x)
        y = raw_dataset['Survived']
        y = y.to_numpy(dtype='float32')

        x_train, x_test, y_train, y_test = self.train_test_split_global(x, y)

        return (x_train, y_train), (x_test, y_test)

    # Model structure and generation
    def generate_new_model(self):
        """Return a LogisticRegression Classifier"""

        clf = self.LogisticRegression()
        clf.classes_ = np.array([0, 1])
        clf.metrics_names = ["log_loss", "Accuracy"]  # Mimic Keras's
        return clf

    # train, test, val splits
    @staticmethod
    def train_test_split_local(x, y):
        return train_test_split(x, y, test_size=0.1, random_state=42)

    @staticmethod
    def train_val_split_local(x, y):
        return train_test_split(x, y, test_size=0.1, random_state=42)

    @staticmethod
    def train_test_split_global(x, y):
        return train_test_split(x, y, test_size=0.1, random_state=42)

    class LogisticRegression(skLR):
        def __init__(self):
            super(Titanic.LogisticRegression, self).__init__(max_iter=10000, warm_start=1, random_state=0)
            self.coef_ = None
            self.intercept_ = None

        def fit(self, x_train, y_train, batch_size, validation_data, epochs=1, verbose=False):
            history = super(Titanic.LogisticRegression, self).fit(x_train, y_train)
            [loss, acc] = self.evaluate(x_train, y_train)
            [val_loss, val_acc] = self.evaluate(*validation_data)
            # Mimic Keras' history
            history.history = {
                'loss': [loss],
                'accuracy': [acc],
                'val_loss': [val_loss],
                'val_accuracy': [val_acc]
            }

            return history

        def evaluate(self, x_eval, y_eval, **kwargs):
            if self.coef_ is None:
                model_evaluation = [0] * 2
            else:
                loss = log_loss(y_eval, self.predict(x_eval))  # mimic keras model evaluation
                accuracy = self.score(x_eval, y_eval)
                model_evaluation = [loss, accuracy]

            return model_evaluation

        def save_weights(self, path):
            if self.coef_ is None:
                raise ValueError(
                    'Coef and intercept are set to None, it seems the model has not been fit properly.')
            if '.h5' in path:
                logger.debug('Automatically switch file format from .h5 to .npy')
                path.replace('.h5', '.npy')
            np.save(path, self.get_weights())

        def load_weights(self, path):
            if '.h5' in path:
                logger.debug('Automatically switch file format from .h5 to .npy')
                path.replace('.h5', '.npy')
            weights = load(path)
            self.set_weights(weights)

        def get_weights(self):
            if self.coef_ is None:
                return None
            else:
                return np.concatenate((self.coef_, self.intercept_.reshape(1, 1)), axis=1)

        def set_weights(self, weights):
            if weights is None:
                self.coef_ = None
                self.intercept_ = None
            else:
                self.coef_ = np.array(weights[0][:-1]).reshape(1, -1)
                self.intercept_ = np.array(weights[0][-1]).reshape(1)

        def save_model(self, path):
            if '.h5' in path:
                logger.debug('Automatically switch file format from .h5 to .joblib')
                path.replace('.h5', '.joblib')
            dump(self, path)

        @staticmethod
        def load_model(path):
            if '.h5' in path:
                logger.debug('Automatically switch file format from .h5 to .joblib')
                path.replace('.h5', '.joblib')
            return load(path)


class Mnist(Dataset):
    def __init__(self):
        # Init dataset-specific variables
        self.img_rows = 28
        self.img_cols = 28
        self.input_shape = (self.img_rows, self.img_cols, 1)
        self.num_classes = 10
        x_test, x_train, y_test, y_train = self.load_data()

        super(Mnist, self).__init__(dataset_name='mnist',
                                    num_classes=self.num_classes,
                                    input_shape=(self.img_rows, self.img_cols, 1),
                                    x_train=x_train,
                                    y_train=y_train,
                                    x_test=x_test,
                                    y_test=y_test
                                    )

    def load_data(self):
        attempts = 0
        while True:
            try:
                (x_train, y_train), (x_test, y_test) = mnist.load_data()
                break
            except (HTTPError, URLError) as e:
                if hasattr(e, 'code'):
                    temp = e.code
                else:
                    temp = e.errno
                logger.debug(
                    f'URL fetch failure on '
                    f'https://s3.amazonaws.com/img-datasets/mnist.npz : '
                    f'{temp} -- {e.reason}')
                if attempts < constants.NUMBER_OF_DOWNLOAD_ATTEMPTS:
                    sleep(2)
                    attempts += 1
                else:
                    raise
        # Pre-process inputs
        x_train = self.preprocess_dataset_inputs(x_train)
        x_test = self.preprocess_dataset_inputs(x_test)
        y_train = self.preprocess_dataset_labels(y_train)
        y_test = self.preprocess_dataset_labels(y_test)
        return x_test, x_train, y_test, y_train

    # Data samples pre-processing method for inputs
    def preprocess_dataset_inputs(self, x):
        x = x.reshape(x.shape[0], self.img_rows, self.img_cols, 1)
        x = x.astype("float32")
        x /= 255

        return x

    # Data samples pre-processing method for labels
    def preprocess_dataset_labels(self, y):
        y = to_categorical(y, self.num_classes)

        return y

    # Model structure and generation
    def generate_new_model(self):
        """Return a CNN model from scratch based on given batch_size"""

        model = Sequential()
        model.add(Conv2D(
            32,
            kernel_size=(3, 3),
            activation="relu",
            input_shape=self.input_shape,
        ))
        model.add(Conv2D(64, (3, 3), activation="relu"))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Flatten())
        model.add(Dense(128, activation="relu"))
        model.add(Dense(self.num_classes, activation="softmax"))

        model.compile(
            loss=categorical_crossentropy,
            optimizer="adam",
            metrics=["accuracy"],
        )

        return model

    # train, test, val splits
    @staticmethod
    def train_test_split_local(x, y):
        return train_test_split(x, y, test_size=0.1, random_state=42)

    @staticmethod
    def train_val_split_local(x, y):
        return train_test_split(x, y, test_size=0.1, random_state=42)


class Imdb(Dataset):
    def __init__(self):
        self.num_words = 5000
        self.num_classes = 2
        self.input_shape = (500,)
        x_test, x_train, y_test, y_train = self.load_data()

        super(Imdb, self).__init__(dataset_name='imdb',
                                   num_classes=self.num_classes,
                                   input_shape=self.input_shape,
                                   x_train=x_train,
                                   y_train=y_train,
                                   x_test=x_test,
                                   y_test=y_test
                                   )

    def load_data(self):
        attempts = 0
        while True:
            try:
                (x_train, y_train), (x_test, y_test) = imdb.load_data(num_words=self.num_words)
                break
            except (HTTPError, URLError) as e:
                if hasattr(e, 'code'):
                    temp = e.code
                else:
                    temp = e.errno
                logger.debug(
                    f'URL fetch failure : '
                    f'{temp} -- {e.reason}')
                if attempts < constants.NUMBER_OF_DOWNLOAD_ATTEMPTS:
                    sleep(2)
                    attempts += 1
                else:
                    raise
        x_train, x_test, y_train, y_test = train_test_split(np.concatenate((x_train, x_test), axis=0),
                                                            np.concatenate((y_train, y_test), axis=0),
                                                            test_size=0.2)
        # Pre-process inputs
        x_train = self.preprocess_dataset_inputs(x_train)
        x_test = self.preprocess_dataset_inputs(x_test)
        y_train = self.preprocess_dataset_labels(y_train)
        y_test = self.preprocess_dataset_labels(y_test)
        return x_test, x_train, y_test, y_train

    @staticmethod
    def preprocess_dataset_labels(y):
        # vanilla label
        return y

    def preprocess_dataset_inputs(self, x):
        x = sequence.pad_sequences(x, maxlen=self.input_shape[0])
        return x

    # Model structure and generation
    def generate_new_model(self):
        """ Return a CNN model from scratch based on given batch_size"""

        model = Sequential()
        model.add(Embedding(self.num_words, 32, input_length=self.input_shape[0]))
        model.add(Conv1D(filters=32,
                         kernel_size=3,
                         padding='same',
                         activation='relu'))
        model.add(MaxPooling1D(pool_size=2))
        model.add(Flatten())
        model.add(Dense(256, activation='relu'))
        model.add(Dropout(0.5))
        model.add(Dense(64, activation='relu'))
        model.add(Dropout(0.5))
        model.add(Dense(1, activation='sigmoid'))

        model.compile(loss='binary_crossentropy',
                      optimizer='adam',
                      metrics=['accuracy'])

        return model

    # train, test, val splits
    @staticmethod
    def train_test_split_local(x, y):
        return x, np.array([]), y, np.array([])

    @staticmethod
    def train_val_split_local(x, y):
        return x, np.array([]), y, np.array([])


class Esc50(Dataset):
    def __init__(self):
        # Load data
        self.num_classes = 50
        self.input_shape = (40, 431, 1)

        (x_train, y_train), (x_test, y_test) = self.load_data()

        super(Esc50, self).__init__(dataset_name='esc50',
                                    num_classes=self.num_classes,
                                    input_shape=self.input_shape,
                                    x_train=x_train,
                                    y_train=y_train,
                                    x_test=x_test,
                                    y_test=y_test
                                    )

    # Init dataset-specific functions

    # Preprocess functions
    def preprocess_dataset_labels(self, y):
        y = to_categorical(y, self.num_classes)

        return y

    def preprocess_dataset_inputs(self, x):
        """
        Compute the Mel-Frequency Cepstral Coefficients
        :param x: iterator. Yield tuples, of audio and rate.
        :return: Array of mfcc images.
        """

        features_list = []
        for audio, rate in x:
            mfccs = mfcc(y=audio, sr=rate, n_mfcc=40)
            # mfccs_scaled = np.mean(mfccs.T, axis=0)
            features_list.append(mfccs)
        features = np.array(features_list)
        return features.reshape(((features.shape[0],) + self.input_shape))

    # download train and test sets
    def load_data(self):
        """
        load the dataset. Note that the x are iterators which need to be preprocess
        :return: (x_train, y_train), (x_test, y_test)
        """
        path = Path(__file__).resolve().parents[0]
        folder = path / 'local_data' / 'esc50'
        if not folder.is_dir():
            Path.mkdir(folder, parents=True)
            logger.info('ESC-50 dataset not found.')
            self._download_data(str(folder))
        else:
            logger.info('ESC-50 dataset found')

        esc50_df = pd.read_csv(folder / 'esc50.csv')
        train, test = self.train_test_split_global(esc50_df)
        y_train = train.target.to_numpy()
        y_test = test.target.to_numpy()
        x_train = (wav_load((folder / 'audio' / file_name).resolve(), sr=None)
                   for file_name in train.filename.to_list())
        x_test = (wav_load((folder / 'audio' / file_name).resolve(), sr=None)
                  for file_name in test.filename.to_list())

        # Pre-process inputs
        logger.info('Preprocessing the raw audios')
        x_train = self.preprocess_dataset_inputs(x_train)
        x_test = self.preprocess_dataset_inputs(x_test)

        y_train = self.preprocess_dataset_labels(y_train)
        y_test = self.preprocess_dataset_labels(y_test)

        return (x_train, y_train), (x_test, y_test)

    @staticmethod
    def _download_data(path):
        """
        Download the dataset, and unzip it. The dataset will be stored in the datasets/local_data directory, which is
        gitignored

        :param path: provided by load_data.
                     Should be LOCAL_DIR/distributed-learning-contributivity/datasets/local_data/esc50
        :return: None
        """
        logger.info('Downloading it from https://github.com/karoldvl/ESC-50/')
        attempts = 0
        while True:
            try:
                urlretrieve('https://github.com/karoldvl/ESC-50/archive/master.zip', f'{path}/ESC-50.zip')
                break
            except (HTTPError, URLError) as e:
                if hasattr(e, 'code'):
                    temp = e.code
                else:
                    temp = e.errno
                logger.debug(
                    f'URL fetch failure on '
                    f'https://github.com/karoldvl/ESC-50/archive/master.zip : '
                    f'{temp} -- {e.reason}')
                if attempts < constants.NUMBER_OF_DOWNLOAD_ATTEMPTS:
                    sleep(2)
                    attempts += 1
                else:
                    raise
        logger.info('Extraction at distributed-learning-contributivity/datasets/local_data/esc50')
        with zipfile.ZipFile(f'{path}/ESC-50.zip') as package:
            package.extractall(f'{path}/')

        Path.unlink(Path(path) / 'ESC-50.zip')
        for src in glob.glob(f'{path}/ESC-50-master/audio'):
            shutil.move(src, f'{path}/{str(Path(src).name)}')
        shutil.move(f'{path}/ESC-50-master/meta/esc50.csv', f'{path}/esc50.csv')

        shutil.rmtree(f'{path}/ESC-50-master')

    # Model structure and generation
    def generate_new_model(self):
        # The model is adapted from https://github.com/mikesmales/Udacity-ML-Capstone
        # It was initially design to work on the URBANSOUND8K DATASET
        model = Sequential()
        model.add(Conv2D(filters=16, kernel_size=2, input_shape=self.input_shape, activation='relu'))
        model.add(MaxPooling2D(pool_size=2))
        model.add(Dropout(0.2))

        model.add(Conv2D(filters=32, kernel_size=2, activation='relu'))
        model.add(MaxPooling2D(pool_size=2))
        model.add(Dropout(0.2))

        model.add(Conv2D(filters=64, kernel_size=2, activation='relu'))
        model.add(MaxPooling2D(pool_size=2))
        model.add(Dropout(0.2))

        model.add(Conv2D(filters=128, kernel_size=2, activation='relu'))
        model.add(MaxPooling2D(pool_size=2))
        model.add(Dropout(0.2))
        model.add(GlobalAveragePooling2D())

        model.add(Dense(self.num_classes, activation='softmax'))
        model.compile(
            loss=categorical_crossentropy,
            optimizer="adam",
            metrics=["accuracy"],
        )
        return model

    # train, test, val splits
    @staticmethod
    def train_test_split_global(data):
        return train_test_split(data, test_size=0.1, random_state=42)
