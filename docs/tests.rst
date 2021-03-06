.. _`testsuite`:

Testsuite
=========

We have implemented 2 types of testsuite: one set of *unit tests* to
test the functionalities of the code and one set of *integration
tests* to test the overall architecture. The latter does actually
deploy a chosen setup and runs several scenarios, simulating how users
will utilize the system as a whole.

Unit Tests
^^^^^^^^^^

Unit tests are minimal: Given a set of input values for a chosen
function, they execute the function and check if the output has the
expected values. Moreover, they capture triggered exceptions and
errors. Additionally we also perform pep8 and pep257 style guide checks
using `flake8  <http://flake8.pycqa.org/en/latest/>`_ with the following
configuration:

.. code-block:: yaml

    [flake8]
    ignore = E226,E302
    exclude =
        docker,
        extras,
        .tox
    max-line-length = 160
    max-complexity = 10

Unit tests can be run using the ``tox`` commands.

.. code-block:: console

    $ cd [git-repo]
    $ tox

Integration Tests
^^^^^^^^^^^^^^^^^

Integration tests are more involved and simulate how a user will use
the system. Therefore, we have develop a `bootstrap script
<bootstrap>`_ to kickstart the system, and we execute a set of scenarii
in it. `The implementation
<https://github.com/NBISweden/LocalEGA/blob/dev/docker/tests/README.md>`_
is in Java, and we target a docker-based environment.

We have grouped the integration around 2 targets: *Common tests* and *Robustness tests*.

.. code-block:: console

    $ cd [git-repo]/docker/tests
    $ mvn test -Dtest=CommonTests -B
    $ mvn test -Dtest=RobustnessTests -B

Scenarii
~~~~~~~~

Here follow the different scenarii we currently test, using a Gherkin-style description.

.. literalinclude:: /../docker/tests/src/test/resources/cucumber/features/authentication.feature
   :language: gherkin
   :lines: 1-20

.. literalinclude:: /../docker/tests/src/test/resources/cucumber/features/ingestion.feature
   :language: gherkin
   :lines: 1-25,38-

.. literalinclude:: /../docker/tests/src/test/resources/cucumber/features/uploading.feature
   :language: gherkin

..
   .. literalinclude:: /../docker/tests/src/test/resources/cucumber/features/checksums.feature
      :language: gherkin

.. literalinclude:: /../docker/tests/src/test/resources/cucumber/features/robustness.feature
   :language: gherkin
   :lines: 1-15
