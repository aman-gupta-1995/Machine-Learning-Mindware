from ConfigSpace.configuration_space import ConfigurationSpace
from ConfigSpace.hyperparameters import UniformFloatHyperparameter
import numpy as np

from mindware.components.models.base_model import BaseClassificationModel
from mindware.components.utils.constants import DENSE, UNSIGNED_DATA, PREDICTIONS
from mindware.components.utils.model_util import softmax


class QDA(BaseClassificationModel):

    def __init__(self, reg_param, random_state=None):
        if reg_param is not None:
            self.reg_param = float(reg_param)
        else:
            self.reg_param = None
        self.estimator = None
        self.time_limit = None
        self.random_state = random_state

    def fit(self, X, Y):
        import sklearn.discriminant_analysis

        estimator = sklearn.discriminant_analysis. \
            QuadraticDiscriminantAnalysis(reg_param=self.reg_param)

        if len(Y.shape) == 2 and Y.shape[1] > 1:
            self.estimator = sklearn.multiclass.OneVsRestClassifier(estimator, n_jobs=1)
        else:
            self.estimator = estimator

        self.estimator.fit(X, Y)

        if len(Y.shape) == 2 and Y.shape[1] > 1:
            problems = []
            for est in self.estimator.estimators_:
                problem = np.any(np.any([np.any(s <= 0.0) for s in
                                         est.scalings_]))
                problems.append(problem)
            problem = np.any(problems)
        else:
            problem = np.any(np.any([np.any(s <= 0.0) for s in
                                     self.estimator.scalings_]))
        if problem:
            raise ValueError('Numerical problems in QDA. QDA.scalings_ '
                             'contains values <= 0.0')
        return self

    def predict(self, X):
        if self.estimator is None:
            raise NotImplementedError()
        return self.estimator.predict(X)

    def predict_proba(self, X):
        if self.estimator is None:
            raise NotImplementedError()

        df = self.estimator.predict_proba(X)
        return softmax(df)

    @staticmethod
    def get_properties(dataset_properties=None):
        return {'shortname': 'QDA',
                'name': 'Quadratic Discriminant Analysis',
                'handles_regression': False,
                'handles_classification': True,
                'handles_multiclass': True,
                'handles_multilabel': True,
                'is_deterministic': True,
                'input': (DENSE, UNSIGNED_DATA),
                'output': (PREDICTIONS,)}

    @staticmethod
    def get_hyperparameter_search_space(dataset_properties=None):
        reg_param = UniformFloatHyperparameter('reg_param', 0.0, 1.0,
                                               default_value=0.0)

        cs = ConfigurationSpace()
        cs.add_hyperparameter(reg_param)
        return cs
