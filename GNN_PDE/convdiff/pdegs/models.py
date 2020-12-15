import torch
import torch.nn as nn
from torch_geometric.nn.conv import MessagePassing


# NNs -> Conv. layers -> GNN -> Dynamics Function


class EdgeConvBase(MessagePassing):
    # Adapted https://pytorch-geometric.readthedocs.io/en/latest/modules/nn.html#torch_geometric.nn.conv.EdgeConv
    def __init__(
        self, 
        msg_net, 
        aggr_net, 
        aggr='mean', 
        neighbor_loc="position", 
        self_val=True, 
        **kwargs,
    ):
        super(EdgeConvBase, self).__init__(aggr=aggr, flow="target_to_source", **kwargs)
        self.msg_net = msg_net
        self.aggr_net = aggr_net
        self.neighbor_loc = neighbor_loc
        self.self_val = self_val
        self.reset_parameters()

    def reset_parameters(self):
        pass

    def forward(self, x, edge_index, pos):
        x = x.unsqueeze(-1) if x.dim() == 1 else x
        return self.propagate(edge_index, x=x, pos=pos)

    def message(self, x_i, x_j, pos_i, pos_j):
        if self.neighbor_loc == "distance":
            dist = (pos_j-pos_i).norm(dim=1).view(-1, 1)
            inputs = torch.cat([x_i, x_j, dist], dim=1)
        elif self.neighbor_loc == "position":
            inputs = torch.cat([x_i, x_j, pos_j-pos_i], dim=1)
        elif self.neighbor_loc == "radial":
            dist = (pos_j - pos_i).norm(dim=1).view(-1, 1)
            pos_vec = pos_j - pos_i
            angle = torch.atan2(pos_vec[:, 1], pos_vec[:, 0]).view(-1, 1)
            inputs = torch.cat([x_i, x_j, dist, angle], dim=1)
        else:
            raise NameError()
        return self.msg_net(inputs)

    def update(self, aggr_out, x):
        if self.self_val:
            inp = torch.cat((x, aggr_out), dim=1)
        else:
            inp = aggr_out
        return self.aggr_net(inp)

    def __repr__(self):
        return '{}(msg_nn={}, aggr_nn={})'.format(
            self.__class__.__name__, self.msg_net, self.aggr_net)


class EdgeConvGeom(EdgeConvBase):  
    def forward(self, edge_index, pos):
        return self.propagate(edge_index, pos=pos)

    def message(self, pos_i, pos_j):
        distances = (pos_j-pos_i).norm(dim=1).reshape(-1, 1)
        positions = (pos_j - pos_i) / distances
        inputs = torch.cat([distances, positions], dim=1)
        return self.msg_net(inputs)

    def update(self, aggr_out):
        return self.aggr_net(aggr_out)


class EdgeConvWithCtx(EdgeConvBase):
    def forward(self, x, edge_index, pos, ctx):
        x = x.unsqueeze(-1) if x.dim() == 1 else x
        return self.propagate(edge_index, x=x, pos=pos, ctx=ctx)

    def message(self, x_i, x_j, pos_i, pos_j, ctx_i):
        distances = (pos_j-pos_i).norm(dim=1).reshape(-1, 1)
        positions = (pos_j - pos_i) / distances
        inputs = torch.cat([x_i, x_j-x_i, distances, positions, ctx_i], dim=1)
        return self.msg_net(inputs)

    def update(self, aggr_out, x, pos, ctx):
        inputs = torch.cat([aggr_out, ctx], dim=1)
        return self.aggr_net(inputs)


# ## M1 and M2 ## 

class MPNNModel(nn.Module):
    def __init__(self, msg_net, aggr_net):
        super(MPNNModel, self).__init__()
        self.L1 = EdgeConvBase(
            msg_net, aggr_net, aggr='mean', neighbor_loc="position", self_val=True)

    def forward(self, x, edge_index, pos):
        return self.L1(x, edge_index.long(), pos)

# ###############


# ##### M3 ######

class M3Model(nn.Module):
    def __init__(self, L1_msg_net, L1_aggr_net, L2_msg_net, L2_aggr_net):
        super(M3Model, self).__init__()
        self.L1 = EdgeConvGeom(L1_msg_net, L1_aggr_net, aggr='mean')
        self.L2 = EdgeConvWithCtx(L2_msg_net, L2_aggr_net, aggr='mean')

    def forward(self, x, edge_index, pos):
        context = self.L1(edge_index.long(), pos)
        return self.L2(x, edge_index.long(), pos, context)

# ###############