from mindware.components.feature_engineering.transformations.base_transformer import *


class DataBalancer(Transformer):
    type = -20

    def __init__(self):
        super().__init__("data_balancer")

    def operate(self, input_datanode, target_fields=None):
        output_datanode = input_datanode.copy_()
        output_datanode.data_balance = 1
        output_datanode.trans_hist.append(self.type)

        return output_datanode
