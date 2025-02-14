"""
createpackages.py is a utility script that reads in the file definition
metadata in the .dfn files and creates the package classes in the modflow
folder. Run this script any time changes are made to the .dfn files.

To create a new package that is part of an existing model, first create a new
dfn file for the package in the mf6/data/dfn folder.
1) Follow the file naming convention <model abbr>-<package abbr>.dfn.
2) Run this script (createpackages.py), and check in your new dfn file, and
   the package class and updated __init__.py that createpackages.py created.

A subpackage is a package referenced by another package (vs being referenced
in the name file).  The tas, ts, and obs packages are examples of subpackages.
There are a few additional steps required when creating a subpackage
definition file.  First, verify that the parent package's dfn file has a file
record for the subpackage to the option block.   For example, for the time
series package the file record definition starts with:

    block options
    name ts_filerecord
    type record ts6 filein ts6_filename

Verify that the same naming convention is followed as the example above,
specifically:

    name <subpackage-abbr>_filerecord
    record <subpackage-abbr>6 filein <subpackage-abbr>6_filename

Next, create the child package definition file in the mf6/data/dfn folder
following the naming convention above.

When your child package is ready for release follow the same procedure as
other packages along with these a few additional steps required for
subpackages.

At the top of the child dfn file add two lines describing how the parent and
child packages are related. The first line determines how the subpackage is
linked to the package:

# flopy subpackage <parent record> <abbreviation> <child data>
<data name>

* Parent record is the MF6 record name of the filerecord in parent package
  that references the child packages file name
* Abbreviation is the short abbreviation of the new subclass
* Child data is the name of the child class data that can be passed in as
  parameter to the parent class. Passing in this parameter to the parent class
  automatically creates the child class with the data provided.
* Data name is the parent class parameter name that automatically creates the
  child class with the data provided.

The example below is the first line from the ts subpackage dfn:

# flopy subpackage ts_filerecord ts timeseries timeseries

The second line determines the variable name of the subpackage's parent and
the type of parent (the parent package's object oriented parent):

# flopy parent_name_type <parent package variable name>
<parent package type>

An example below is the second line in the ts subpackage dfn:

# flopy parent_name_type parent_package MFPackage

There are three possible types (or combination of them) that can be used for
"parent package type", MFPackage, MFModel, and MFSimulation. If a package
supports multiple types of parents (for example, it can be either in the model
namefile or in a package, like the obs package), include all the types
supported, seperating each type with a / (MFPackage/MFModel).

To create a new type of model choose a unique three letter model abbreviation
("gwf", "gwt", ...). Create a name file dfn with the naming convention
<model abbr>-nam.dfn. The name file must have only an options and packages
block (see gwf-nam.dfn as an example). Create a new dfn file for each of the
packages in your new model, following the naming convention described above.

When your model is ready for release make sure all the dfn files are in the
flopy/mf6/data/dfn folder, run createpackages.py, and check in your new dfn
files, the package classes, and updated init.py that createpackages.py created.

"""

import datetime
import os
import textwrap
from enum import Enum

# keep below as absolute imports
from flopy.mf6.data import mfdatautil, mfstructure
from flopy.utils import datautil


class PackageLevel(Enum):
    sim_level = 0
    model_level = 1


def build_doc_string(param_name, param_type, param_desc, indent):
    return f"{indent}{param_name} : {param_type}\n{indent * 2}* {param_desc}"


def generator_type(data_type):
    if (
        data_type == mfstructure.DataType.scalar_keyword
        or data_type == mfstructure.DataType.scalar
    ):
        # regular scalar
        return "ScalarTemplateGenerator"
    elif (
        data_type == mfstructure.DataType.scalar_keyword_transient
        or data_type == mfstructure.DataType.scalar_transient
    ):
        # transient scalar
        return "ScalarTemplateGenerator"
    elif data_type == mfstructure.DataType.array:
        # array
        return "ArrayTemplateGenerator"
    elif data_type == mfstructure.DataType.array_transient:
        # transient array
        return "ArrayTemplateGenerator"
    elif data_type == mfstructure.DataType.list:
        # list
        return "ListTemplateGenerator"
    elif (
        data_type == mfstructure.DataType.list_transient
        or data_type == mfstructure.DataType.list_multiple
    ):
        # transient or multiple list
        return "ListTemplateGenerator"


def clean_class_string(name):
    if len(name) > 0:
        clean_string = name.replace(" ", "_")
        clean_string = clean_string.replace("-", "_")
        version = mfstructure.MFStructure().get_version_string()
        # FIX: remove all numbers
        if clean_string[-1] == version:
            clean_string = clean_string[:-1]
        return clean_string
    return name


def build_dfn_string(dfn_list, header, package_abbr, flopy_dict):
    dfn_string = "    dfn = ["
    line_length = len(dfn_string)
    leading_spaces = " " * line_length
    first_di = True

    # process header
    dfn_string = f'{dfn_string}\n{leading_spaces}["header", '
    for key, value in header.items():
        if key == "multi-package":
            dfn_string = f'{dfn_string}\n{leading_spaces} "multi-package", '
        if key == "netcdf":
            dfn_string = f'{dfn_string}\n{leading_spaces} "netcdf", '
        if key == "package-type":
            dfn_string = (
                f'{dfn_string}\n{leading_spaces} "package-type ' f'{value}"'
            )

    # process solution packages
    if package_abbr in flopy_dict["solution_packages"]:
        model_types = '", "'.join(
            flopy_dict["solution_packages"][package_abbr]
        )
        dfn_string = (
            f"{dfn_string}\n{leading_spaces} "
            f'["solution_package", "{model_types}"], '
        )
    dfn_string = f"{dfn_string}],\n{leading_spaces}"

    # process all data items
    for data_item in dfn_list:
        line_length += 1
        if not first_di:
            dfn_string = f"{dfn_string},\n{leading_spaces}"
            line_length = len(leading_spaces)
        else:
            first_di = False
        dfn_string = f"{dfn_string}["
        first_line = True
        # process each line in a data item
        for line in data_item:
            line = line.strip()
            # do not include the description of longname
            if not line.lower().startswith(
                "description"
            ) and not line.lower().startswith("longname"):
                line = line.replace('"', "'")
                line_length += len(line) + 4
                if not first_line:
                    dfn_string = f"{dfn_string},"
                if line_length < 77:
                    # added text fits on the current line
                    if first_line:
                        dfn_string = f'{dfn_string}"{line}"'
                    else:
                        dfn_string = f'{dfn_string} "{line}"'
                else:
                    # added text does not fit on the current line
                    line_length = len(line) + len(leading_spaces) + 2
                    if line_length > 79:
                        # added text too long to fit on a single line, wrap
                        # text as needed
                        line = f'"{line}"'
                        lines = textwrap.wrap(
                            line,
                            75 - len(leading_spaces),
                            drop_whitespace=True,
                        )
                        lines[0] = f"{leading_spaces} {lines[0]}"
                        line_join = f' "\n{leading_spaces} "'
                        dfn_string = f"{dfn_string}\n{line_join.join(lines)}"
                    else:
                        dfn_string = f'{dfn_string}\n{leading_spaces} "{line}"'
            first_line = False

        dfn_string = f"{dfn_string}]"
    dfn_string = f"{dfn_string}]"
    return dfn_string


def create_init_var(clean_ds_name, data_structure_name, init_val=None):
    if init_val is None:
        init_val = clean_ds_name

    init_var = f"        self.{clean_ds_name} = self.build_mfdata("
    leading_spaces = " " * len(init_var)
    if len(init_var) + len(data_structure_name) + 2 > 79:
        second_line = f'\n            "{data_structure_name}",'
        if len(second_line) + len(clean_ds_name) + 2 > 79:
            init_var = f"{init_var}{second_line}\n            {init_val})"
        else:
            init_var = f"{init_var}{second_line} {init_val})"
    else:
        init_var = f'{init_var}"{data_structure_name}",'
        if len(init_var) + len(clean_ds_name) + 2 > 79:
            init_var = f"{init_var}\n{leading_spaces}{init_val})"
        else:
            init_var = f"{init_var} {init_val})"
    return init_var


def create_basic_init(clean_ds_name):
    return f"        self.{clean_ds_name} = {clean_ds_name}\n"


def create_property(clean_ds_name):
    return f"    {clean_ds_name} = property(get_{clean_ds_name}, set_{clean_ds_name})"


def format_var_list(base_string, var_list, is_tuple=False):
    if is_tuple:
        base_string = f"{base_string}("
        extra_chars = 4
    else:
        extra_chars = 2
    line_length = len(base_string)
    leading_spaces = " " * line_length
    # determine if any variable name is too long to fit
    for item in var_list:
        if line_length + len(item) + extra_chars > 80:
            leading_spaces = "        "
            base_string = f"{base_string}\n{leading_spaces}"
            line_length = len(leading_spaces)
            break

    for index, item in enumerate(var_list):
        if is_tuple:
            item = f"'{item}'"
        if index == len(var_list) - 1:
            next_var_str = item
        else:
            next_var_str = f"{item},"
        line_length += len(item) + extra_chars
        if line_length > 80:
            base_string = f"{base_string}\n{leading_spaces}{next_var_str}"
        else:
            if base_string[-1] == ",":
                base_string = f"{base_string} "
            base_string = f"{base_string}{next_var_str}"
    if is_tuple:
        return f"{base_string}))"
    else:
        return f"{base_string})"


def create_package_init_var(
    parameter_name, package_abbr, data_name, clean_ds_name
):
    one_line = (
        f"        self._{package_abbr}_package = self.build_child_package("
    )
    one_line_b = f'"{package_abbr}", {parameter_name},'
    leading_spaces = " " * len(one_line)
    two_line = f'\n{leading_spaces}"{data_name}",'
    three_line = f"\n{leading_spaces}self._{clean_ds_name})"
    return f"{one_line}{one_line_b}{two_line}{three_line}"


def add_var(
    init_vars,
    class_vars,
    options_param_list,
    init_param_list,
    package_properties,
    doc_string,
    data_structure_dict,
    default_value,
    name,
    python_name,
    description,
    path,
    data_type,
    basic_init=False,
    construct_package=None,
    construct_data=None,
    parameter_name=None,
    set_param_list=None,
):
    if set_param_list is None:
        set_param_list = []
    clean_ds_name = datautil.clean_name(python_name)
    if construct_package is None:
        # add variable initialization lines
        if basic_init:
            init_vars.append(create_basic_init(clean_ds_name))
        else:
            init_vars.append(create_init_var(clean_ds_name, name))
        # add to parameter list
        if default_value is None:
            default_value = "None"
        init_param_list.append(f"{clean_ds_name}={default_value}")
        if path is not None and "options" in path:
            options_param_list.append(f"{clean_ds_name}={default_value}")
        # add to set parameter list
        set_param_list.append(f"{clean_ds_name}={clean_ds_name}")
    else:
        clean_parameter_name = datautil.clean_name(parameter_name)
        # init hidden variable
        init_vars.append(create_init_var(f"_{clean_ds_name}", name, "None"))
        # init child package
        init_vars.append(
            create_package_init_var(
                clean_parameter_name,
                construct_package,
                construct_data,
                clean_ds_name,
            )
        )
        # add to parameter list
        init_param_list.append(f"{clean_parameter_name}=None")
        # add to set parameter list
        set_param_list.append(f"{clean_parameter_name}={clean_parameter_name}")

    package_properties.append(create_property(clean_ds_name))
    doc_string.add_parameter(description, model_parameter=True)
    data_structure_dict[python_name] = 0
    if class_vars is not None:
        gen_type = generator_type(data_type)
        if gen_type != "ScalarTemplateGenerator":
            new_class_var = f"    {clean_ds_name} = {gen_type}("
            class_vars.append(format_var_list(new_class_var, path, True))
            return gen_type
    return None


def build_init_string(
    init_string, init_param_list, whitespace="                 "
):
    line_chars = len(init_string)
    for index, param in enumerate(init_param_list):
        if index + 1 < len(init_param_list):
            line_chars += len(param) + 2
        else:
            line_chars += len(param) + 3
        if line_chars > 79:
            if len(param) + len(whitespace) + 1 > 79:
                # try to break apart at = sign
                param_list = param.split("=")
                if len(param_list) == 2:
                    init_string = "{},\n{}{}=\n{}{}".format(
                        init_string,
                        whitespace,
                        param_list[0],
                        whitespace,
                        param_list[1],
                    )
                    line_chars = len(param_list[1]) + len(whitespace) + 1
                    continue
            init_string = f"{init_string},\n{whitespace}{param}"
            line_chars = len(param) + len(whitespace) + 1
        else:
            init_string = f"{init_string}, {param}"
    return f"{init_string}):\n"


def build_model_load(model_type):
    model_load_c = (
        "    Methods\n    -------\n"
        "    load : (simulation : MFSimulationData, model_name : "
        "string,\n        namfile : string, "
        "version : string, exe_name : string,\n        model_ws : "
        "string, strict : boolean) : MFSimulation\n"
        "        a class method that loads a model from files"
        '\n    """'
    )

    model_load = (
        "    @classmethod\n    def load(cls, simulation, structure, "
        "modelname='NewModel',\n             "
        "model_nam_file='modflowtest.nam', version='mf6',\n"
        "             exe_name='mf6', strict=True, "
        "model_rel_path='.',\n"
        "             load_only=None):\n        "
        "return mfmodel.MFModel.load_base(cls, simulation, structure, "
        "modelname,\n                                         "
        "model_nam_file, '{}6', version,\n"
        "                                         exe_name, strict, "
        "model_rel_path,\n"
        "                                         load_only)"
        "\n".format(model_type)
    )
    return model_load, model_load_c


def build_sim_load():
    sim_load_c = (
        "    Methods\n    -------\n"
        "    load : (sim_name : str, version : "
        "string,\n        exe_name : str or PathLike, "
        "sim_ws : str or PathLike, strict : bool,\n        verbosity_level : "
        "int, load_only : list, verify_data : bool,\n        "
        "write_headers : bool, lazy_io : bool, use_pandas : bool,\n        "
        ") : MFSimulation\n"
        "        a class method that loads a simulation from files"
        '\n    """'
    )

    sim_load = (
        "    @classmethod\n    def load(cls, sim_name='modflowsim', "
        "version='mf6',\n             "
        "exe_name: Union[str, os.PathLike] = 'mf6',\n             "
        "sim_ws: Union[str, os.PathLike] = os.curdir,\n             "
        "strict=True, verbosity_level=1, load_only=None,\n             "
        "verify_data=False, write_headers=True,\n             "
        "lazy_io=False, use_pandas=True):\n        "
        "return mfsimbase.MFSimulationBase.load(cls, sim_name, version, "
        "\n                                               "
        "exe_name, sim_ws, strict,\n"
        "                                               verbosity_level, "
        "load_only,\n                                               "
        "verify_data, write_headers, "
        "\n                                               lazy_io, use_pandas)"
        "\n"
    )
    return sim_load, sim_load_c


def build_model_init_vars(param_list):
    init_var_list = []
    # build set data calls
    for param in param_list:
        param_parts = param.split("=")
        init_var_list.append(
            f"        self.name_file.{param_parts[0]}.set_data({param_parts[0]})"
        )
    init_var_list.append("")
    # build attributes
    for param in param_list:
        param_parts = param.split("=")
        init_var_list.append(
            f"        self.{param_parts[0]} = self.name_file.{param_parts[0]}"
        )

    return "\n".join(init_var_list)


def create_packages():
    indent = "    "
    init_string_def = "    def __init__(self"

    # load JSON file
    file_structure = mfstructure.MFStructure(load_from_dfn_files=True)
    sim_struct = file_structure.sim_struct

    # assemble package list of buildable packages
    package_list = []
    package_list.append(
        (
            sim_struct.name_file_struct_obj,
            PackageLevel.sim_level,
            "",
            sim_struct.name_file_struct_obj.dfn_list,
            sim_struct.name_file_struct_obj.file_type,
            sim_struct.name_file_struct_obj.header,
        )
    )
    for package in sim_struct.package_struct_objs.values():
        # add simulation level package to list
        package_list.append(
            (
                package,
                PackageLevel.sim_level,
                "",
                package.dfn_list,
                package.file_type,
                package.header,
            )
        )
    for package in sim_struct.utl_struct_objs.values():
        # add utility packages to list
        package_list.append(
            (
                package,
                PackageLevel.model_level,
                "utl",
                package.dfn_list,
                package.file_type,
                package.header,
            )
        )
    for model_key, model in sim_struct.model_struct_objs.items():
        package_list.append(
            (
                model.name_file_struct_obj,
                PackageLevel.model_level,
                model_key,
                model.name_file_struct_obj.dfn_list,
                model.name_file_struct_obj.file_type,
                model.name_file_struct_obj.header,
            )
        )
        for package in model.package_struct_objs.values():
            package_list.append(
                (
                    package,
                    PackageLevel.model_level,
                    model_key,
                    package.dfn_list,
                    package.file_type,
                    package.header,
                )
            )

    util_path, tail = os.path.split(os.path.realpath(__file__))
    init_file = open(
        os.path.join(util_path, "..", "modflow", "__init__.py"),
        "w",
        newline="\n",
    )
    init_file.write("from .mfsimulation import MFSimulation  # isort:skip\n")

    nam_import_string = (
        "from .. import mfmodel\nfrom ..data.mfdatautil "
        "import ArrayTemplateGenerator, ListTemplateGenerator"
    )

    # loop through packages list
    init_file_imports = []
    flopy_dict = file_structure.flopy_dict
    for package in package_list:
        data_structure_dict = {}
        package_properties = []
        init_vars = []
        init_param_list = []
        options_param_list = []
        set_param_list = []
        class_vars = []
        template_gens = []
        package_abbr = clean_class_string(
            f"{clean_class_string(package[2])}{package[0].file_type}"
        ).lower()
        dfn_string = build_dfn_string(
            package[3], package[5], package_abbr, flopy_dict
        )
        package_name = clean_class_string(
            "{}{}{}".format(
                clean_class_string(package[2]),
                package[0].file_prefix,
                package[0].file_type,
            )
        ).lower()
        if package[0].description:
            doc_string = mfdatautil.MFDocString(package[0].description)
        else:
            if package[2]:
                package_container_text = f" within a {package[2]} model"
            else:
                package_container_text = ""
            ds = "Modflow{} defines a {} package{}.".format(
                package_name.title(),
                package[0].file_type,
                package_container_text,
            )
            if package[0].file_type == "mvr":
                # mvr package warning
                if package[2]:
                    ds = (
                        "{} This package\n    can only be used to move "
                        "water between packages within a single model."
                        "\n    To move water between models use ModflowMvr"
                        ".".format(ds)
                    )
                else:
                    ds = (
                        "{} This package can only be used to move\n    "
                        "water between two different models. To move "
                        "water between two packages\n    in the same "
                        'model use the "model level" mover package (ex. '
                        "ModflowGwfmvr).".format(ds)
                    )

            doc_string = mfdatautil.MFDocString(ds)

        if package[0].dfn_type == mfstructure.DfnType.exch_file:
            exgtype = (
                f'"{package_abbr[0:3].upper()}6-{package_abbr[3:].upper()}6"'
            )

            add_var(
                init_vars,
                None,
                options_param_list,
                init_param_list,
                package_properties,
                doc_string,
                data_structure_dict,
                exgtype,
                "exgtype",
                "exgtype",
                build_doc_string(
                    "exgtype",
                    "<string>",
                    "is the exchange type (GWF-GWF or GWF-GWT).",
                    indent,
                ),
                None,
                None,
                True,
            )
            add_var(
                init_vars,
                None,
                options_param_list,
                init_param_list,
                package_properties,
                doc_string,
                data_structure_dict,
                None,
                "exgmnamea",
                "exgmnamea",
                build_doc_string(
                    "exgmnamea",
                    "<string>",
                    "is the name of the first model that is "
                    "part of this exchange.",
                    indent,
                ),
                None,
                None,
                True,
            )
            add_var(
                init_vars,
                None,
                options_param_list,
                init_param_list,
                package_properties,
                doc_string,
                data_structure_dict,
                None,
                "exgmnameb",
                "exgmnameb",
                build_doc_string(
                    "exgmnameb",
                    "<string>",
                    "is the name of the second model that is "
                    "part of this exchange.",
                    indent,
                ),
                None,
                None,
                True,
            )
            init_vars.append(
                "        simulation.register_exchange_file(self)\n"
            )

        # loop through all blocks
        for block in package[0].blocks.values():
            for data_structure in block.data_structures.values():
                # only create one property for each unique data structure name
                if data_structure.name not in data_structure_dict:
                    tg = add_var(
                        init_vars,
                        class_vars,
                        options_param_list,
                        init_param_list,
                        package_properties,
                        doc_string,
                        data_structure_dict,
                        data_structure.default_value,
                        data_structure.name,
                        data_structure.python_name,
                        data_structure.get_doc_string(79, indent, indent),
                        data_structure.path,
                        data_structure.get_datatype(),
                        False,
                        data_structure.construct_package,
                        data_structure.construct_data,
                        data_structure.parameter_name,
                        set_param_list,
                    )
                    if tg is not None and tg not in template_gens:
                        template_gens.append(tg)

        import_string = "from .. import mfpackage"
        if template_gens:
            import_string += "\nfrom ..data.mfdatautil import "
            import_string += ", ".join(sorted(template_gens))
        # add extra docstrings for additional variables
        doc_string.add_parameter(
            "    filename : String\n        File name for this package."
        )
        doc_string.add_parameter(
            "    pname : String\n        Package name for this package."
        )
        doc_string.add_parameter(
            "    parent_file : MFPackage\n        "
            "Parent package file that references this "
            "package. Only needed for\n        utility "
            "packages (mfutl*). For example, mfutllaktab "
            "package must have \n        a mfgwflak "
            "package parent_file."
        )

        # build package builder class string
        init_vars.append("        self._init_complete = True")
        init_vars = "\n".join(init_vars)
        package_short_name = clean_class_string(package[0].file_type).lower()
        class_def_string = "class Modflow{}(mfpackage.MFPackage):\n".format(
            package_name.title()
        )
        class_def_string = class_def_string.replace("-", "_")
        class_var_string = (
            '{}\n    package_abbr = "{}"\n    _package_type = '
            '"{}"\n    dfn_file_name = "{}"'
            "\n".format(
                "\n".join(class_vars),
                package_abbr,
                package[4],
                package[0].dfn_file_name,
            )
        )
        init_string_full = init_string_def
        init_string_sim = f"{init_string_def}, simulation"
        # add variables to init string
        doc_string.add_parameter(
            "    loading_package : bool\n        "
            "Do not set this parameter. It is intended "
            "for debugging and internal\n        "
            "processing purposes only.",
            beginning_of_list=True,
        )
        if "parent_name_type" in package[0].header:
            init_var = package[0].header["parent_name_type"][0]
            parent_type = package[0].header["parent_name_type"][1]
        elif package[1] == PackageLevel.sim_level:
            init_var = "simulation"
            parent_type = "MFSimulation"
        else:
            init_var = "model"
            parent_type = "MFModel"
        doc_string.add_parameter(
            f"    {init_var} : {parent_type}\n        "
            f"{init_var.capitalize()} that this package is a part "
            "of. Package is automatically\n        "
            f"added to {init_var} when it is "
            "initialized.",
            beginning_of_list=True,
        )
        init_string_full = (
            f"{init_string_full}, {init_var}, loading_package=False"
        )
        init_param_list.append("filename=None")
        init_param_list.append("pname=None")
        init_param_list.append("**kwargs")
        init_string_full = build_init_string(init_string_full, init_param_list)

        # build init code
        parent_init_string = "        super().__init__("
        spaces = " " * len(parent_init_string)
        parent_init_string = (
            '{}{}, "{}", filename, pname,\n{}'
            "loading_package, **kwargs)\n\n"
            "        # set up variables".format(
                parent_init_string, init_var, package_short_name, spaces
            )
        )
        local_datetime = datetime.datetime.now(datetime.timezone.utc)
        comment_string = (
            "# DO NOT MODIFY THIS FILE DIRECTLY.  THIS FILE "
            "MUST BE CREATED BY\n# mf6/utils/createpackages.py\n"
            "# FILE created on {} UTC".format(
                local_datetime.strftime("%B %d, %Y %H:%M:%S")
            )
        )
        # assemble full package string
        package_string = "{}\n{}\n\n\n{}{}\n{}\n{}\n\n{}{}\n{}\n".format(
            comment_string,
            import_string,
            class_def_string,
            doc_string.get_doc_string(),
            class_var_string,
            dfn_string,
            init_string_full,
            parent_init_string,
            init_vars,
        )

        # open new Packages file
        pb_file = open(
            os.path.join(util_path, "..", "modflow", f"mf{package_name}.py"),
            "w",
            newline="\n",
        )
        pb_file.write(package_string)

        if package[0].sub_package and package_abbr != "utltab":
            set_param_list.append("filename=filename")
            set_param_list.append("pname=pname")
            set_param_list.append("child_builder_call=True")
            whsp_1 = "                   "
            whsp_2 = "                                    "

            file_prefix = package[0].dfn_file_name[0:3]
            chld_doc_string = (
                '    """\n    {}Packages is a container '
                "class for the Modflow{} class.\n\n    "
                "Methods\n    ----------"
                "\n".format(package_name.title(), package_name.title())
            )

            # write out child packages class
            chld_cls = (
                "\n\nclass {}Packages(mfpackage.MFChildPackage" "s):\n".format(
                    package_name.title()
                )
            )
            chld_var = (
                f"    package_abbr = "
                f'"{package_name.title().lower()}packages"\n\n'
            )
            chld_init = "    def initialize(self"
            chld_init = build_init_string(
                chld_init, init_param_list[:-1], whsp_1
            )
            init_pkg = "\n        self.init_package(new_package, filename)"
            params_init = (
                "        new_package = Modflow"
                f"{package_name.title()}(self._cpparent"
            )
            params_init = build_init_string(
                params_init, set_param_list, whsp_2
            )
            chld_doc_string = (
                "{}    initialize\n        Initializes a new "
                "Modflow{} package removing any sibling "
                "child\n        packages attached to the same "
                "parent package. See Modflow{} init\n "
                "       documentation for definition of "
                "parameters.\n".format(
                    chld_doc_string, package_name.title(), package_name.title()
                )
            )

            chld_appn = ""
            params_appn = ""
            append_pkg = ""
            if package_abbr != "utlobs":  # Hard coded obs no multi-pkg support
                chld_appn = "\n\n    def append_package(self"
                chld_appn = build_init_string(
                    chld_appn, init_param_list[:-1], whsp_1
                )
                append_pkg = (
                    "\n        self._append_package(new_package, filename)"
                )
                params_appn = (
                    "        new_package = Modflow"
                    f"{file_prefix.capitalize()}"
                    f"{package_short_name}(self._cpparent"
                )
                params_appn = build_init_string(
                    params_appn, set_param_list, whsp_2
                )
                chld_doc_string = (
                    "{}    append_package\n        Adds a "
                    "new Modflow{}{} package to the container."
                    " See Modflow{}{}\n        init "
                    "documentation for definition of "
                    "parameters.\n".format(
                        chld_doc_string,
                        file_prefix.capitalize(),
                        package_short_name,
                        file_prefix.capitalize(),
                        package_short_name,
                    )
                )
            chld_doc_string = f'{chld_doc_string}    """\n'
            packages_str = "{}{}{}{}{}{}{}{}{}\n".format(
                chld_cls,
                chld_doc_string,
                chld_var,
                chld_init,
                params_init[:-2],
                init_pkg,
                chld_appn,
                params_appn[:-2],
                append_pkg,
            )
            pb_file.write(packages_str)
        pb_file.close()

        init_file_imports.append(
            f"from .mf{package_name} import Modflow{package_name.title()}\n"
        )

        if package[0].dfn_type == mfstructure.DfnType.model_name_file:
            # build model file
            init_vars = build_model_init_vars(options_param_list)

            options_param_list.insert(0, "model_rel_path='.'")
            options_param_list.insert(0, "exe_name='mf6'")
            options_param_list.insert(0, "version='mf6'")
            options_param_list.insert(0, "model_nam_file=None")
            options_param_list.insert(0, "modelname='model'")
            options_param_list.append("**kwargs,")
            init_string_sim = build_init_string(
                init_string_sim, options_param_list
            )
            sim_name = clean_class_string(package[2])
            class_def_string = "class Modflow{}(mfmodel.MFModel):\n".format(
                sim_name.capitalize()
            )
            class_def_string = class_def_string.replace("-", "_")
            doc_string.add_parameter(
                "    sim : MFSimulation\n        "
                "Simulation that this model is a part "
                "of.  Model is automatically\n        "
                "added to simulation when it is "
                "initialized.",
                beginning_of_list=True,
                model_parameter=True,
            )
            doc_string.description = (
                f"Modflow{sim_name} defines a {sim_name} model"
            )
            class_var_string = f"    model_type = '{sim_name}'\n"
            mparent_init_string = "        super().__init__("
            spaces = " " * len(mparent_init_string)
            mparent_init_string = (
                "{}simulation, model_type='{}6',\n{}"
                "modelname=modelname,\n{}"
                "model_nam_file=model_nam_file,\n{}"
                "version=version, exe_name=exe_name,\n{}"
                "model_rel_path=model_rel_path,\n{}"
                "**kwargs,"
                ")\n".format(
                    mparent_init_string,
                    sim_name,
                    spaces,
                    spaces,
                    spaces,
                    spaces,
                    spaces,
                )
            )
            load_txt, doc_text = build_model_load(sim_name)
            package_string = "{}\n{}\n\n\n{}{}\n{}\n{}\n{}{}\n{}\n\n{}".format(
                comment_string,
                nam_import_string,
                class_def_string,
                doc_string.get_doc_string(True),
                doc_text,
                class_var_string,
                init_string_sim,
                mparent_init_string,
                init_vars,
                load_txt,
            )
            md_file = open(
                os.path.join(util_path, "..", "modflow", f"mf{sim_name}.py"),
                "w",
                newline="\n",
            )
            md_file.write(package_string)
            md_file.close()
            init_file_imports.append(
                f"from .mf{sim_name} import Modflow{sim_name.capitalize()}\n"
            )
        elif package[0].dfn_type == mfstructure.DfnType.sim_name_file:
            # build simulation file
            init_vars = build_model_init_vars(options_param_list)

            options_param_list.insert(0, "lazy_io=False")
            options_param_list.insert(0, "use_pandas=True")
            options_param_list.insert(0, "write_headers=True")
            options_param_list.insert(0, "verbosity_level=1")
            options_param_list.insert(
                0, "sim_ws: Union[str, os.PathLike] = " "os.curdir"
            )
            options_param_list.insert(
                0, "exe_name: Union[str, os.PathLike] " '= "mf6"'
            )
            options_param_list.insert(0, "version='mf6'")
            options_param_list.insert(0, "sim_name='sim'")
            init_string_sim = "    def __init__(self"
            init_string_sim = build_init_string(
                init_string_sim, options_param_list
            )
            class_def_string = (
                "class MFSimulation(mfsimbase." "MFSimulationBase):\n"
            )
            doc_string.add_parameter(
                "    sim_name : str\n" "       Name of the simulation",
                beginning_of_list=True,
                model_parameter=True,
            )
            doc_string.description = (
                "MFSimulation is used to load, build, and/or save a MODFLOW "
                "6 simulation. \n    A MFSimulation object must be created "
                "before creating any of the MODFLOW 6 \n    model objects."
            )
            sparent_init_string = "        super().__init__("
            spaces = " " * len(sparent_init_string)
            sparent_init_string = (
                "{}sim_name=sim_name,\n{}"
                "version=version,\n{}"
                "exe_name=exe_name,\n{}"
                "sim_ws=sim_ws,\n{}"
                "verbosity_level=verbosity_level,\n{}"
                "write_headers=write_headers,\n{}"
                "lazy_io=lazy_io,\n{}"
                "use_pandas=use_pandas,\n{}"
                ")\n".format(
                    sparent_init_string,
                    spaces,
                    spaces,
                    spaces,
                    spaces,
                    spaces,
                    spaces,
                    spaces,
                    spaces,
                )
            )
            sim_import_string = (
                "import os\n"
                "from typing import Union\n"
                "from .. import mfsimbase"
            )

            load_txt, doc_text = build_sim_load()
            package_string = "{}\n{}\n\n\n{}{}\n{}\n{}{}\n{}\n\n{}".format(
                comment_string,
                sim_import_string,
                class_def_string,
                doc_string.get_doc_string(False, True),
                doc_text,
                init_string_sim,
                sparent_init_string,
                init_vars,
                load_txt,
            )
            sim_file = open(
                os.path.join(util_path, "..", "modflow", "mfsimulation.py"),
                "w",
                newline="\n",
            )
            sim_file.write(package_string)
            sim_file.close()
            init_file_imports.append(
                "from .mfsimulation import MFSimulation\n"
            )

    # Sort the imports
    for line in sorted(init_file_imports, key=lambda x: x.split()[3]):
        init_file.write(line)
    init_file.close()


if __name__ == "__main__":
    create_packages()
