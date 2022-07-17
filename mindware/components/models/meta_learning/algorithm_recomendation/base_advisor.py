import os
import hashlib
import numpy as np
import pickle as pkl
from collections import OrderedDict
from mindware.datasets.utils import calculate_metafeatures
from mindware.utils.logging_utils import get_logger
from mindware.components.utils.constants import CLS_TASKS, RGS_TASKS
from mindware.components.meta_learning.algorithm_recomendation.metadata_manager import MetaDataManager
from mindware.components.meta_learning.algorithm_recomendation.metadata_manager import get_feature_vector

_cls_builtin_algorithms = ['lightgbm', 'random_forest', 'libsvm_svc', 'extra_trees', 'liblinear_svc',
                           'k_nearest_neighbors', 'adaboost', 'lda', 'qda']
_rgs_builtin_algorithms = ['lightgbm', 'random_forest', 'libsvm_svr', 'extra_trees', 'liblinear_svr',
                           'k_nearest_neighbors', 'adaboost', 'lasso_regression', 'gradient_boosting']


class BaseAdvisor(object):
    def __init__(self, n_algorithm=3,
                 task_type=None,
                 metric='bal_acc',
                 rep=3,
                 total_resource=1200,
                 meta_algorithm='lightgbm',
                 exclude_datasets=None,
                 meta_dir=None):
        self.logger = get_logger(self.__module__ + "." + self.__class__.__name__)
        self.n_algorithm = n_algorithm
        self.n_algo_candidates = len(_cls_builtin_algorithms)
        self.task_type = task_type
        self.meta_algo = meta_algorithm
        self.rep = rep
        self.metric = metric
        if task_type in CLS_TASKS:
            self.algorithms = _cls_builtin_algorithms
            self.n_algo_candidates = len(_cls_builtin_algorithms)
            if metric not in ['acc', 'bal_acc']:
                self.logger.info('Meta information about metric-%s does not exist, use accuracy instead.' % str(metric))
                metric = 'acc'
        elif task_type in RGS_TASKS:
            self.algorithms = _rgs_builtin_algorithms
            self.n_algo_candidates = len(_rgs_builtin_algorithms)
            if metric not in ['mse']:
                self.logger.info('Meta information about metric-%s does not exist, use accuracy instead.' % str(metric))
                metric = 'mse'
        else:
            raise ValueError('Invalid metric: %s.' % metric)

        self.total_resource = total_resource
        self.exclude_datasets = exclude_datasets

        builtin_loc = os.path.dirname(__file__)
        builtin_loc = os.path.join(builtin_loc, '..')
        builtin_loc = os.path.join(builtin_loc, 'meta_resource')
        self.meta_dir = meta_dir if meta_dir is not None else builtin_loc

        if self.exclude_datasets is None:
            self.hash_id = 'none'
        else:
            self.exclude_datasets = list(set(exclude_datasets))
            exclude_str = ','.join(sorted(self.exclude_datasets))
            md5 = hashlib.md5()
            md5.update(exclude_str.encode('utf-8'))
            self.hash_id = md5.hexdigest()
        meta_datasets = set()
        _folder = os.path.join(self.meta_dir, 'meta_dataset_vec')

        if task_type in CLS_TASKS:
            task_prefix = 'cls'
        else:
            task_prefix = 'rgs'

        embedding_path = os.path.join(_folder, '%s_meta_dataset_embedding.pkl' % task_prefix)
        with open(embedding_path, 'rb')as f:
            d = pkl.load(f)
            meta_datasets = d['task_ids']

        self._builtin_datasets = sorted(list(meta_datasets))

        self.metadata_manager = MetaDataManager(self.meta_dir, self.algorithms, self._builtin_datasets,
                                                metric, total_resource, task_type=task_type, rep=rep)
        self.meta_learner = None

    def fetch_algorithm_set(self, dataset, datanode=None):
        input_vector = get_feature_vector(dataset, task_type=self.task_type)
        if input_vector is None:
            input_dict = calculate_metafeatures(dataset=datanode, task_type=self.task_type)
            sorted_keys = sorted(input_dict.keys())
            input_vector = [input_dict[key] for key in sorted_keys]
        preds = self.predict(input_vector)
        idxs = np.argsort(-preds)
        return [self.algorithms[idx] for idx in idxs]

    def fetch_run_results(self, dataset):
        scores = self.metadata_manager.fetch_meta_runs(dataset)
        idxs = np.argsort(-scores)
        sorted_algos = [self.algorithms[idx] for idx in idxs]
        sorted_scores = [scores[idx] for idx in idxs]
        return OrderedDict(zip(sorted_algos, sorted_scores))

    def fit(self):
        raise NotImplementedError()

    def predict(self, X):
        raise NotImplementedError()
