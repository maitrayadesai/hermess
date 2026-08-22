.. _installation:

Installation
============

Follow these steps to install and set up the ``hermess`` package.

Prerequisites
-------------
Before proceeding, ensure you have the following installed:

- Python 3.10 or later



Installation Steps
------------------

1. Clone the repository:

   .. code-block:: bash

      git clone https://github.com/maitrayadesai/hermess
      cd hermess

2. Install dependencies:

   .. code-block:: bash

      pip install -r requirements.txt



You are now ready to use the ``hermess`` package.


Verifying Installation
----------------------

To verify the installation:

1. Run the main script to ensure everything is working:

   .. code-block:: bash

      python -m hermess



2. If default figures of the simulated dynamic and algebraic states are plotted, the installation was successful.



.. figure:: _static/voltage.png
   :alt: Example PDF Page 1
   :width: 600px

   Figure 1: Simulated voltage magnitudes.

.. figure:: _static/diffstates.png
   :alt: Example PDF Page 2
   :width: 600px

   Figure 2: Simulated internal differential states.


Troubleshooting
---------------
- If you encounter issues during installation, verify that all prerequisites are installed.
- If dependency conflicts occur, try updating your package manager or using a clean Python environment.
- Ensure that you are in the correct directory when running the script.
