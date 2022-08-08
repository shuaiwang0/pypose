from numpy import vectorize
import torch as torch
import torch.nn as nn
from torch.autograd.functional import jacobian

class _System(nn.Module):
    r'''
    A sub-class of :obj:`torch.nn.Module` to build general dynamics.
    
    Args:
        time (:obj:`boolean`): Whether the system is time-varying; defaults to False, meaning time-invariant

    Linearization
    ----------
    The nonlinear state-space equation is given as:

    .. math::
        \begin{align}
        \overrightarrow{x}_{k+1} &= \mathbf{f}(\overrightarrow{x}_k,\overrightarrow{u}_k) \\
        \overrightarrow{y}_{k} &= \mathbf{g}(\overrightarrow{x}_k,\overrightarrow{u}_k)
        \end{align}

    This class provides a means to linearize the system at any point along a trajectory.
    \bf{Note}: The linearization can be provided for any arbitrary point, not just the equilibrium point(s).

    Suppose we to linearize about :math:`(\overrightarrow{x}^*,\overrightarrow{u}^*)`
    for an arbitrary equation :math:`h(x,u)`.
    Through a Taylor series expansion (ignoring higher order terms), we get the following:

    .. math::
        h(x^*,u^*) = \left. \frac{\partial h}{\partial x} \right|_{x^*,u^*} x^* +
                     \left. \frac{\partial h}{\partial u} \right|_{x^*,u^*} u^* + c
    
    Where :math:`c` is the bias generated due to the system not being at an equilibrium point.
    If :math:`(x^*,u^*)` specify an equilibrium point, then :math:`c=0`.
    Applying this to our state-space equations, i.e., Eqs. (1) and (2), we get:

    .. math::
        \begin{align}
        \overrightarrow{x}_{k+1} &= \mathbf{f}(\overrightarrow{x}_k,\overrightarrow{u}_k) = 
        \left. \frac{\partial \mathbf{f}}{\partial \overrightarrow{x}} \right|_{\overrightarrow{x}_k,\overrightarrow{u}_k} \overrightarrow{x}_k +
        \left. \frac{\partial \mathbf{f}}{\partial \overrightarrow{u}} \right|_{\overrightarrow{x}_k,\overrightarrow{u}_k} \overrightarrow{u}_k + c_1 \\
        \overrightarrow{y}_{k} &= \mathbf{g}(\overrightarrow{x}_k,\overrightarrow{u}_k) = 
        \left. \frac{\partial \mathbf{g}}{\partial \overrightarrow{x}} \right|_{\overrightarrow{x}_k,\overrightarrow{u}_k} \overrightarrow{x}_k +
        \left. \frac{\partial \mathbf{g}}{\partial \overrightarrow{u}} \right|_{\overrightarrow{x}_k,\overrightarrow{u}_k} \overrightarrow{u}_k + c_2
        \end{align}

    
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
        r'''
        Parameters
        ----------
        state : Tensor
                The state of the dynamic system
        input : Tensor
                The input to the dynamic system

        Returns
        -------
        new_state   : Tensor
                      The state of the system at next time step
        observation : Tensor
                      The observation of the system at the current step
        '''

        new_state = self.state_transition(state, input)
        observation = self.observation(state, input)
        return new_state, observation

    def state_transition(self, state, input):
        r'''
        Parameters
        ----------
        state : Tensor
                The state of the dynamic system
        input : Tensor
                The input to the dynamic system
                
        Returns
        ----------
        new_state   : Tensor
                      The state of the system at next time step
        '''
        raise NotImplementedError("The users need to define their own state transition method")

    def observation(self, state, input):
        r'''
        Parameters
        ----------
        state : Tensor
                The state of the dynamic system
        input : Tensor
                The input to the dynamic system

        Returns
        ----------
        observation : Tensor
                      The observation of the system at the current step
        '''
        raise NotImplementedError("The users need to define their own observation method")

    def reset(self,t=0):
        self.t.fill_(0) 

    def set_linearization_point(self, state, input):
        r'''
        Function to set the point about which the system is to be linearized.

        Parameters
        ----------
        state : Tensor
                The state of the dynamic system
        input : Tensor
                The input to the dynamic system

        Returns
        ----------
        None
        '''
        self.state, self.input = state, input

    @property
    def A(self):
        r'''
        Parameters
        ----------
        None
        
        Returns
        ----------
        State matrix for linear/linearized system (A)
        '''
        if hasattr(self, '_A'):
            return self._A
        else:
            func = lambda x: self.state_transition(x, self.input)
            return jacobian(func, self.state, **self.jacargs)

    @property
    def B(self):
        r'''
        Parameters
        ----------
        None
        
        Returns
        ----------
        Input matrix for linear/linearized system (B)
        '''
        if hasattr(self, '_B'):
            return self._B
        else:
            func = lambda x: self.state_transition(self.state, x)
            return jacobian(func, self.input, **self.jacargs)

    @property
    def C(self):
        r'''
        Parameters
        ----------
        None
        
        Returns
        ----------
        Output matrix for linear/linearized system (C)
        '''
        if hasattr(self, '_C'):
            return self._C
        else:
            func = lambda x: self.observation(x, self.input)
            return jacobian(func, self.state, **self.jacargs)
 
    @property
    def D(self):
        r'''
        Parameters
        ----------
        None
        
        Returns
        ----------
        Feedthrough matrix for linear/linearized system (D)
        '''
        if hasattr(self, '_D'):
            return self._D
        else:
            func = lambda x: self.observation(self.state, x)
            return jacobian(func, self.input, **self.jacargs)
    
    @property
    def c1(self):
        r'''
        Parameters
        ----------
        None
        
        Returns
        ----------
        Bias generated by state-transition (:math:`c_1`)
        '''
        if hasattr(self,'_c1'):
            return self._c1
        else:
            return self.state_transition(self.state,self.input)-(self.state).matmul(self.A.mT)-(self.input).matmul(self.B.mT)
    
    @property
    def c2(self):
        r'''
        Parameters
        ----------
        None
        
        Returns
        ----------
        Bias generated by observation (:math:`c_2`)
        '''
        if hasattr(self,'_c2'):
            return self._c2
        else:
            return self.observation(self.state,self.input)-(self.state).matmul(self.C.mT)-(self.input).matmul(self.D.mT)

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