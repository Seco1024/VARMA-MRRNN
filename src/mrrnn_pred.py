import numpy as np
import pandas as pd
import random
import datetime
import argparse
import logging
import os
import torch
import torch.nn as nn
from sklearn.metrics import mean_squared_error, mean_absolute_error
from utils.mrrnn_tools import MutuallyRecursiveRNN
from utils import rnn_tools
random.seed()

logging.basicConfig(level=logging.CRITICAL)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

parent_dir = os.path.abspath(os.path.join(os.getcwd(), os.path.pardir))
files_dir = os.path.join(parent_dir, f'data/VARMA_ARIMA/after_ARIMA_full/')
tmp_dir = os.path.join(parent_dir, 'data/VARMA_ARIMA_prediction/after_ARIMA_full/')
pred_target = os.listdir(files_dir)[int(len(os.listdir(files_dir))*0.9):]
observed_target = ['2303_2379.csv', '2303_2308.csv', '2308_2357.csv', '2317_2379.csv', '2382_2454.csv']

today = rnn_tools.get_today()
if not os.path.exists(os.path.join(parent_dir, f'models/{str(today)}')):
    today = datetime.datetime.strptime(today, '%m%d') - datetime.timedelta(days=1)
    today = datetime.datetime.strftime(today, '%m%d')
    
parser = argparse.ArgumentParser()
parser.add_argument("--cell", default='lstm')
parser.add_argument("--neurons", default=32, help="number of neurons")
parser.add_argument("--double_layer", default=0, help="is double layered")
parser.add_argument("--dropout", default=0.5, help="Dropout Rate")
parser.add_argument("--lr", default=0.0005, help="learning rate")
parser.add_argument("--lookback", default=14)
parser.add_argument("--date", default=today)
args = parser.parse_args()
    
hybrid_prediction_mse, hybrid_prediction_mae, arima_prediction_mae, arima_prediction_mse = [], [], [], []
lookback = int(args.lookback)
future_n = 1

sample_file = os.listdir(tmp_dir)[0]
sample_df = pd.read_csv(os.path.join(tmp_dir, sample_file), index_col='date', parse_dates=True)
features_dim = len(sample_df.columns)

# load model
mrrnn = MutuallyRecursiveRNN(features_dim, 1, features_dim - 1,
    int(int(args.neurons) / features_dim),
    int(int(args.neurons) * (features_dim - 1) / features_dim),
    float(args.dropout),
    cell=args.cell
)
mrrnn.load_state_dict(torch.load(os.path.join(parent_dir,
            f"models/{str(args.date)}/MRRNN_{args.cell}_{args.neurons}_{args.dropout}.pt")))
mrrnn.eval()

for file in pred_target:
    residual_file_path = os.path.join(files_dir, file)
    residual_df = pd.read_csv(residual_file_path, index_col='date', parse_dates=True)
    residual_df = residual_df.reset_index(drop=True)
    arima_output_path = os.path.join(parent_dir, f'data/VARMA_ARIMA_prediction/after_ARIMA_full/{file}')
    arima_output_df = pd.read_csv(arima_output_path, index_col='date', parse_dates=True)
    arima_output_df = arima_output_df.reset_index(drop=True)
    arima_output_df = arima_output_df['close']
    original_path = os.path.join(parent_dir, f'data/preprocessed_data_full/{file}')
    original_df = pd.read_csv(original_path, index_col='date', parse_dates=True)
    timestamps = original_df.index
    original_df = original_df.reset_index(drop=True)
    original_df = original_df['close']
    original_df = original_df[-len(arima_output_df):]
    
    residual_X, arima_prediction, original, rnn_prediction = [], [], [], []
    for i in range(lookback, len(residual_df) - future_n + 1):
        residual_X.append(residual_df[i - lookback:i])
    residual_X = np.array([residual_X[i].values.tolist() for i in range(len(residual_X))])
    
    with torch.no_grad():
        residual_X_tensor = []
        test_mse, test_mae = 0, 0
        residual_X_tensor = torch.Tensor(residual_X)
        
        price_pred, metrics_pred = mrrnn(residual_X_tensor)
        mrrnn_prediction = price_pred.numpy().flatten()
        arima_prediction = arima_output_df[-len(mrrnn_prediction):].tolist()
        original = original_df[-len(mrrnn_prediction):].tolist()
        timestamps = timestamps[-len(mrrnn_prediction):].tolist()
        mrrnn_prediction = mrrnn_prediction.tolist()
        hybrid_prediction = [x - y for x, y in zip(arima_prediction, mrrnn_prediction)]
    
        arima_prediction_mse.append(mean_squared_error(original, arima_prediction))
        arima_prediction_mae.append(mean_absolute_error(original, arima_prediction))
        hybrid_prediction_mse.append(mean_squared_error(original, hybrid_prediction))
        hybrid_prediction_mae.append(mean_absolute_error(original, hybrid_prediction))
    
    if file in observed_target:
        mrrnn.visualize_prediction_plot(hybrid_prediction, original, arima_prediction, timestamps, args.date, file)

df_error = pd.DataFrame(columns=['ARIMA prediction MSE', 'ARIMA prediction MAE', 'ARIMA_MRRNN prediction MSE', 'ARIMA_MRRNN prediction MAE'])
df_error.loc[0] = rnn_tools.mean(arima_prediction_mse), rnn_tools.mean(arima_prediction_mae), rnn_tools.mean(hybrid_prediction_mse), rnn_tools.mean(hybrid_prediction_mae)
df_error.to_csv(os.path.join(parent_dir, f'out/hybrid_model_error/{str(args.date)}/ARIMA-MRRNN({args.cell})_{str(args.neurons)}_{str(args.dropout)}.csv'))