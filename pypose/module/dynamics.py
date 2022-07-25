from numpy import vectorize
import torch as torch
import torch.nn as nn
from torch.autograd.functional import jacobian


class _System(nn.Module):                                                # DH: Please follow the documentation style in LTI to document this class.
    r'''
    A sub-class of :obj:`torch.nn.Module` to build general dynamics.
    
    Args:
        time (:obj:`boolean`): Whether the system is time-varying; defaults to False, meaning time-invariant
    '''
    def __init__(self, time=False):
        super().__init__()
        self.jacargs = {'vectorize':True, 'strategy':'reverse-mode'}
        if time:
            self.register_buffer('t',torch.zeros(1))
            self.register_forward_hook(self.forward_hook)

    def forward_hook(self, module, inputs, outputs):
        self.input, self.state = inputs
        self.t.add_(1)

    def forward(self, state, input):
        new_state = self.state_transition(state, input)
        return new_state, self.observation(state, input)

    def state_transition(self):
        pass

    def observation(self):
        pass

    def reset(self,t=0):
        self.t.fill_(0) 

    def set_linearization_point(self, state, input):
        self.state, self.input = state, input

    @property
    def A(self):
        if hasattr(self, '_A'):
            return self._A
        else:
            func = lambda x: self.state_transition(x, self.input)            # DH: TYPO.  So has the Jacobian been ever tested yet??
            return jacobian(func, self.state, **self.jacargs)

    @property
    def B(self):
        if hasattr(self, '_B'):
            return self._B
        else:
            func = lambda x: self.state_transition(self.state, x)
            return jacobian(func, self.input, **self.jacargs)

    @property
    def C(self):
        if hasattr(self, '_C'):
            return self._C
        else:
            func = lambda x: self.observation(x, self.input)
            return jacobian(func, self.state, **self.jacargs)
 
    @property
    def D(self):
        if hasattr(self, '_D'):
            return self._D
        else:
            func = lambda x: self.observation(self.state, x)
            return jacobian(func, self.input, **self.jacargs)


class LTI(_System):
    r'''
    A sub-class of: obj: '_System' to represent Linear Time-Invariant system.
    
    Args:
        A, B, C, D (:obj:`Tensor`): The input tensor in the state-space equation of LTI system,
            usually in matrix form.
        c1, c2 (:obj:`Tensor`): Bias generated by system.
        
    Note:
        According to the actual physical meaning, the dimensions of A, B, C, D must be the same,
        whether in the batch case or not.
        
        The system is time invariant.
    '''
    def __init__(self, A, B, C, D, c1=None, c2=None):
        super(LTI, self).__init__(time=False)
        assert A.ndim == B.ndim == C.ndim == D.ndim, "Invalid System Matrices dimensions"
        self._A, self._B, self._C, self._D = A, B, C, D
        self._c1, self._c2 = c1, c2

    @property
    def c1(self):
        return self._c1
    
    @property
    def c2(self):
        return self._c2
    
    def forward(self, x, u):
        r'''
        Parameters
        ----------
        x : Tensor
            The state of LTI system
        u : Tensor
            The input of LTI system

        Returns
        -------
        z : Tensor
            Derivative of x in discrete case, state-transition
        y : Tensor
            The output of LTI system, observation
            
        Every linear time-invariant lumped system can be described by a set of equations of the form
        which is called the state-space equation.
        
        .. math::
            \begin{align*}
                z_{i} = A_{i} \times x_{i} + B_{i} \times u_{i} + c_1
                y_{i} = C_{i} \times x_{i} + D_{i} \times u_{i} + c_2
            \end{align*}
            
        where :math:`\mathbf{z}` is actually :math:`\mathbf{\dot{x}}`, the differential form of :math:`\mathbf{x}`
        
        Let the input be matrix :math:`\mathbf{A}`, :math:`\mathbf{B}`, :math:`\mathbf{C}`, :math:`\mathbf{D}`, :math:`\mathbf{x}`, :math:`\mathbf{u}`.
        :math:`\mathbf{x}_i` represents each individual matrix in the batch. 
        
        Note:
            -x, u could be single input or multiple inputs

            -A, B, C, D can only be two-dimensional matrices or the batch
             In the batch case, their dimensions must be the same as those of u, x 
             A, B, C, D and u, x are multiplied separately for each channel.
             
            -For a System with p inputs, q outputs, and n state variables,
             A, B, C, D are n*n n*p q*n and q*p constant matrices.
             
            -Note that variables are entered as row vectors.

        Example:
            >>> A = torch.randn((3,3))
                B = torch.randn((3,2))
                C = torch.randn((3,3))
                D = torch.randn((3,2))
                c1 = torch.randn((2,1,3))
                c2 = torch.randn((2,1,3))
                x = torch.randn((2,1,3))
                u = torch.randn((2,1,2))
            >>> A
            tensor([[ 0.3925, -0.1799, -0.0653],
                    [-0.6016,  1.9318,  1.1651],
                    [-0.3182,  1.4565,  1.0184]]) 
                B
            tensor([[-0.4794, -1.7299],
                    [-1.1820, -0.0606],
                    [-1.2021, -0.5444]]) 
                C
            tensor([[-0.1721,  1.6730, -0.6955],
                    [-0.4956,  1.3174,  0.3740],
                    [-0.0835,  0.3706, -1.9351]])
                D
            tensor([[ 1.9300e-01, -1.3445e+00],
                    [ 2.6992e-01, -9.1387e-01],
                    [-6.3274e-04,  5.1283e-01]]) 
                c1
            tensor([[[-0.8519, -0.6737, -0.3359]],
                    [[ 0.5543, -0.1456,  1.4389]]]) 
                c2
            tensor([[[-0.7543, -0.6047, -0.6620]],
                    [[ 0.6252,  2.6831, -3.1711]]]) 
                x
            tensor([[[ 1.0022, -0.1371,  1.0773]],
                    [[ 0.7227,  0.7777,  1.0332]]]) 
                u
            tensor([[[1.7736, 0.7472]],
                    [[0.4841, 0.9187]]])
            >>> lti = LTI(A, B, C, D, c1, c2)
            tensor([[[-1.7951, -1.7544, -1.9603]],
                    [[-1.7451,  1.6436,  0.8730]]]), 
            tensor([[[-1.8134, -0.4785, -1.8370]],
                    [[-0.6836,  0.3439, -1.3006]]]))
    
        Note:
            In this general example, all variables are in the batch. User definable as appropriate.
            
        '''

        if self.A.ndim >= 3:
            assert self.A.ndim == x.ndim == u.ndim,  "Invalid System Matrices dimensions"
        else:
            assert self.A.ndim == 2,  "Invalid System Matrices dimensions"

        z = x.matmul(self.A.mT) + u.matmul(self.B.mT) + self.c1
        y = x.matmul(self.C.mT) + u.matmul(self.D.mT) + self.c2

        return z, y

# class CartPole(_System):                                                      # DH: These are examples and should not appear here.  Make a file in pypose/test/ and run the test there.
#                                                                               # DH: Same story for cartpoleTest and NNTest.  And are the tests for Jacobians written yet?
#     def __init__(self,dt,length,cartmass,polemass,gravity):
#         super().__init__(self)
#         self._tau = dt
#         self._length = length
#         self._cartmass = cartmass
#         self._polemass = polemass
#         self._gravity = gravity
#         self._polemassLength = self._polemass*self._length
#         self._totalMass = self._cartmass + self._polemass

#     def state_transition(self,state,input):
#         x,xDot,theta,thetaDot = state
#         force = input
#         costheta = torch.cos(theta)
#         sintheta = torch.sin(theta)

#         temp = (
#             force + self._polemassLength * thetaDot**2 * sintheta
#         ) / self._totalMass
#         thetaAcc = (self._gravity * sintheta - costheta * temp) / (
#             self._length * (4.0 / 3.0 - self._polemass * costheta**2 / self._totalMass)
#         )
#         xAcc = temp - self._polemassLength * thetaAcc * costheta / self._totalMass

#         _dstate = torch.stack((xDot,xAcc,thetaDot,thetaAcc))

#         return state+torch.mul(_dstate,self._tau),self.observation(state,input)
    
#     def observation(self,state,input):
#         return state

# class LorenzAttractor(_System):
#     def __init__(self,dt,model):
#         super().__init__(self)
#         self._tau = dt
#         self._stateTransition = model
    
#     def forward(self,state,input):
#         self._dstate = self.state_transition(state,input)
#         return self.observation(state,input)

#     def state_transition(self,state,input):
#         return self._stateTransition(state)
    
#     def observation(self,state,input):
#         return state + torch.mul(self._dstate,self._tau)

#     def loss(self,pred,true):
#         return torch.sqrt(torch.sum((pred-true)**2)/pred.size(dim=0))
