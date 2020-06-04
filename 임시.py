import pandas as pd
import numpy as np
from tqdm import tqdm
import random
import tensorflow as tf
import matplotlib.pyplot as plt
import os

from tensorflow.keras.layers import LSTM, Dense
from tensorflow.keras import Model
from tensorflow.keras import Sequential


def mse_AIFrenz(y_true, y_pred):
    diff = abs(y_true - y_pred)
    less_then_one = np.where(diff < 1, 0, diff)
    # multi-column일 경우에도 계산 할 수 있도록 np.average를 한번 더 씌움
    try:
        score = np.average(np.average(less_then_one ** 2, axis = 0))
    except ValueError:
        score = mean_squared_error(y_true, y_pred)
    return score


def mse_keras(y_true, y_pred):
    score = tf.py_function(func=mse_AIFrenz, inp=[y_true, y_pred], Tout=tf.float32,  name='custom_mse') # tf 2.x
    # score = tf.py_func( lambda y_true, y_pred : mse_AIFrenz(y_true, y_pred) , [y_true, y_pred], 'float32', stateful = False, name = 'custom_mse' ) # tf 1.x
    return score


def convert_to_timeseries(df, interval):
    sequence_list = []
    target_list = []
    
    for i in tqdm(range(df.shape[0] - interval)):
        sequence_list.append(np.array(df.iloc[i:i+interval,:-1]))
        target_list.append(df.iloc[i+interval,-1])
    
    sequence = np.array(sequence_list)
    target = np.array(target_list)
    
    return sequence, target


train = pd.read_csv('train.csv', index_col='id')
test = pd.read_csv('test.csv', index_col='id')

# 기상청 데이터만 추출
x_train = train.loc[:, 'X00':'X39']

# standardization을 위해 평균과 표준편차 구하기
MEAN = x_train.mean()
STD = x_train.std()

# 표준편차가 0일 경우 대비하여 1e-07 추가 
x_train = (x_train - MEAN) / (STD + 1e-07)

y_columns = ['Y15','Y16']

# t시점 이전 120분의 데이터로 t시점의 온도를 추정할 수 있는 학습데이터 형성
sequence = np.empty((0, 12, 40))
target = np.empty((0,))
for column in y_columns :
    
    concat = pd.concat([x_train, train[column]], axis = 1)

    _sequence, _target = convert_to_timeseries(concat.head(144*30), interval = 12)

    sequence = np.vstack((sequence, _sequence))
    target = np.hstack((target, _target))

# convert_to_timeseries 함수를 쓰기 위한 dummy feature 생성
x_train['dummy'] = 0

# train set에서 도출된 평균과 표준편차로 standardization 실시 
test = (test - MEAN) / (STD + 1e-07)

# convert_to_timeseries 함수를 쓰기 위한 dummy feature 생성
test['dummy'] = 0

# train과 test 기간을 합쳐서 120분 간격으로 학습데이터 재구축
x_test, _ = convert_to_timeseries(pd.concat([x_train, test], axis=0), interval=12)

# test set 기간인 후반부 80일에 맞게 자르기 
x_test = x_test[-11520:, :, :]

# 만들어 두었던 dummy feature 제거
x_train.drop('dummy', axis=1, inplace=True)
test.drop('dummy', axis=1, inplace=True)

# 간단한 lstm 모델 구축하기 
model = tf.keras.models.Sequential([
    tf.keras.layers.LSTM(256, input_shape=sequence.shape[-2:]),
    tf.keras.layers.Dense(128, activation='linear'),
    tf.keras.layers.Dense(64, activation='linear'),
    tf.keras.layers.Dense(1)
])

model.compile(optimizer='adam', loss='mse', metrics=[mse_keras])


# loss가 n미만으로 떨어지면 학습 종료 시키는 기능
class MyCallback(tf.keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs=None):
        if logs.get('loss') < 3:
            print('\n Loss is under 3, cancelling training')
            self.model.stop_training = True


callbacks = MyCallback()

# 모델 학습
model.fit(    
    sequence, target,
    epochs=100,
    batch_size=128,
    verbose=2,
    shuffle=False,
    callbacks=[callbacks]
)

# LSTM 레이어는 고정
model.layers[0].trainable = False

# fine tuning 할 때 사용할 학습데이터 생성 (Y18)
finetune_x, finetune_y = convert_to_timeseries(pd.concat([x_train.tail(432), train['Y18'].tail(432)], axis=1), interval=12)

# LSTM 레이어는 고정 시켜두고, DNN 레이어에 대해서 fine tuning 진행 (Transfer Learning)
ft_model = model.fit(
            finetune_x, finetune_y,
            epochs=100,
            batch_size=64,
            shuffle=False,
            verbose=2)

# 예측하기 
pred_y = model.predict(x_test)

# 제출 파일 만들기
submit = pd.DataFrame({'id': range(144*33, 144*113), 'Y18': pred_y.reshape(1, -1)[0]})

submit.to_csv('submit3.csv', index=False)
