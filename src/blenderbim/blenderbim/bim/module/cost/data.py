# BlenderBIM Add-on - OpenBIM Blender Add-on
# Copyright (C) 2023 Dion Moult <dion@thinkmoult.com>
#
# This file is part of BlenderBIM Add-on.
#
# BlenderBIM Add-on is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BlenderBIM Add-on is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BlenderBIM Add-on.  If not, see <http://www.gnu.org/licenses/>.

import bpy
import ifcopenshell
import ifcopenshell.util.cost
import ifcopenshell.util.element
import blenderbim.tool as tool
import blenderbim.bim.schema
from ifcopenshell.util.doc import get_entity_doc, get_predefined_type_doc


def refresh():
    CostSchedulesData.is_loaded = False
    CostItemRatesData.is_loaded = False
    CostItemQuantitiesData.is_loaded = False


class CostSchedulesData:
    data = {}
    is_loaded = False

    @classmethod
    def load(cls):
        cls.data = {
            "predefined_types": cls.get_cost_schedule_types(),
            "total_cost_schedules": cls.total_cost_schedules(),
            "schedules": cls.schedules(),
            "is_editing_rates": cls.is_editing_rates(),
            "cost_items": cls.cost_items(),
            "cost_quantities": cls.cost_quantities(),
            "cost_values": cls.cost_values(),
            "quantity_types": cls.quantity_types(),
        }
        cls.is_loaded = True

    @classmethod
    def total_cost_schedules(cls):
        return len(tool.Ifc.get().by_type("IfcCostSchedule"))

    @classmethod
    def schedules(cls):
        results = []
        if bpy.context.scene.BIMCostProperties.active_cost_schedule_id:
            schedule = tool.Ifc.get().by_id(bpy.context.scene.BIMCostProperties.active_cost_schedule_id)
            results.append(
                {
                    "id": schedule.id(),
                    "name": schedule.Name or "Unnamed",
                }
            )
        else:
            for schedule in tool.Ifc.get().by_type("IfcCostSchedule"):
                results.append(
                    {
                        "id": schedule.id(),
                        "name": schedule.Name or "Unnamed",
                    }
                )
        return results

    @classmethod
    def is_editing_rates(cls):
        ifc_id = bpy.context.scene.BIMCostProperties.active_cost_schedule_id
        if not ifc_id:
            return
        return tool.Ifc.get().by_id(ifc_id).PredefinedType == "SCHEDULEOFRATES"

    @classmethod
    def cost_items(cls):
        cls._cost_values = {}
        results = {}
        for cost_item in tool.Ifc.get().by_type("IfcCostItem"):
            data = {}
            cls._load_cost_item_quantities(cost_item, data)
            cls._load_cost_values(cost_item, data)
            results[cost_item.id()] = data
        return results

    @classmethod
    def _load_cost_values(cls, root_element, data):
        # data["CostValues"] = []
        data["CategoryValues"] = {}
        data["UnitBasisValueComponent"] = None
        data["UnitBasisUnitSymbol"] = None
        data["TotalAppliedValue"] = 0.0
        data["TotalCost"] = 0.0
        if root_element.is_a("IfcCostItem"):
            values = root_element.CostValues
        elif root_element.is_a("IfcConstructionResource"):
            values = root_element.BaseCosts
        for cost_value in values or []:
            cls._load_cost_value(root_element, data, cost_value)
            # data["CostValues"].append(cost_value.id())
            data["TotalAppliedValue"] += cls._cost_values[cost_value.id()]["AppliedValue"]
            if cost_value.UnitBasis:
                cost_value_data = cls._cost_values[cost_value.id()]
                data["UnitBasisValueComponent"] = cost_value_data["UnitBasis"]["ValueComponent"]
                data["UnitBasisUnitSymbol"] = cost_value_data["UnitBasis"]["UnitSymbol"]
        if data["UnitBasisValueComponent"]:
            data["TotalCost"] = data["TotalCostQuantity"] / data["UnitBasisValueComponent"] * data["TotalAppliedValue"]
        else:
            data["TotalCost"] = data["TotalCostQuantity"] * data["TotalAppliedValue"]

    @classmethod
    def _load_cost_item_quantities(cls, cost_item, data):
        parametric_quantities = []
        for rel in cost_item.Controls:
            for related_object in rel.RelatedObjects or []:
                quantities = cls._get_object_quantities(cost_item, related_object)
                # data["Controls"][related_object.id()] = quantities
                parametric_quantities.extend(quantities)

        # data["CostQuantities"] = []
        data["TotalCostQuantity"] = ifcopenshell.util.cost.get_total_quantity(cost_item)
        for quantity in cost_item.CostQuantities or []:
            if quantity.id() in parametric_quantities:
                continue
            # quantity_data = quantity.get_info()
            # del quantity_data["Unit"]
            # cls.physical_quantities[quantity.id()] = quantity_data
            # data["CostQuantities"].append(quantity.id())
        # data["Unit"] = None
        data["UnitSymbol"] = "?"
        if cost_item.CostQuantities:
            quantity = cost_item.CostQuantities[0]
            unit = ifcopenshell.util.unit.get_property_unit(quantity, tool.Ifc.get())
            if unit:
                # data["Unit"] = unit.id()
                data["UnitSymbol"] = ifcopenshell.util.unit.get_unit_symbol(unit)
            else:
                # data["Unit"] = None
                data["UnitSymbol"] = None

    @classmethod
    def _get_object_quantities(cls, cost_item, element):
        if not element.is_a("IfcObject"):
            return []
        results = []
        for relationship in element.IsDefinedBy:
            if not relationship.is_a("IfcRelDefinesByProperties"):
                continue
            qto = relationship.RelatingPropertyDefinition
            if not qto.is_a("IfcElementQuantity"):
                continue
            for prop in qto.Quantities:
                if prop in cost_item.CostQuantities or []:
                    results.append(prop.id())
        return results

    @classmethod
    def _load_cost_value(cls, root_element, root_element_data, cost_value):
        value_data = cost_value.get_info()
        del value_data["AppliedValue"]
        if value_data["UnitBasis"]:
            data = cost_value.UnitBasis.get_info()
            data["ValueComponent"] = data["ValueComponent"].wrappedValue
            data["UnitComponent"] = data["UnitComponent"].id()
            data["UnitSymbol"] = ifcopenshell.util.unit.get_unit_symbol(cost_value.UnitBasis.UnitComponent)
            value_data["UnitBasis"] = data
        if value_data["ApplicableDate"]:
            value_data["ApplicableDate"] = ifcopenshell.util.date.ifc2datetime(value_data["ApplicableDate"])
        if value_data["FixedUntilDate"]:
            value_data["FixedUntilDate"] = ifcopenshell.util.date.ifc2datetime(value_data["FixedUntilDate"])
        value_data["Components"] = [c.id() for c in value_data["Components"] or []]
        value_data["AppliedValue"] = ifcopenshell.util.cost.calculate_applied_value(root_element, cost_value)

        if cost_value.Category not in [None, "*"]:
            root_element_data["CategoryValues"].setdefault(cost_value.Category, 0)
            root_element_data["CategoryValues"][cost_value.Category] += value_data["AppliedValue"]

        value_data["Formula"] = ifcopenshell.util.cost.serialise_cost_value(cost_value)

        cls._cost_values[cost_value.id()] = value_data
        for component in cost_value.Components or []:
            cls._load_cost_value(root_element, root_element_data, component)

    @classmethod
    def cost_quantities(cls):
        results = []
        ifc_id = bpy.context.scene.BIMCostProperties.active_cost_item_id
        if not ifc_id:
            return results
        for quantity in tool.Ifc.get().by_id(ifc_id).CostQuantities or []:
            results.append({"id": quantity.id(), "name": quantity.Name, "value": "{0:.2f}".format(quantity[3])})
        return results

    @classmethod
    def cost_values(cls):
        results = []
        ifc_id = bpy.context.scene.BIMCostProperties.active_cost_item_id
        if not ifc_id:
            return results
        cost_item = tool.Ifc.get().by_id(ifc_id)
        for cost_value in cost_item.CostValues or []:
            label = "{0:.2f}".format(ifcopenshell.util.cost.calculate_applied_value(cost_item, cost_value))
            label += " = {}".format(ifcopenshell.util.cost.serialise_cost_value(cost_value))
            results.append({"id": cost_value.id(), "label": label})
        return results

    @classmethod
    def quantity_types(cls):
        return [
            (t.name(), t.name(), "")
            for t in tool.Ifc.schema().declaration_by_name("IfcPhysicalSimpleQuantity").subtypes()
        ]

    @classmethod
    def get_cost_schedule_types(cls):
        results = []
        declaration = tool.Ifc().schema().declaration_by_name("IfcCostSchedule")
        version = tool.Ifc.get_schema()
        for attribute in declaration.attributes():
            if attribute.name() == "PredefinedType":
                results.extend(
                    [
                        (e, e, get_predefined_type_doc(version, "IfcCostSchedule", e))
                        for e in attribute.type_of_attribute().declared_type().enumeration_items()
                    ]
                )
                break
        return results

class CostItemRatesData:
    data = {}
    is_loaded = False

    @classmethod
    def load(cls):
        cls.data = {
            "schedule_of_rates": cls.schedule_of_rates(),
        }
        cls.is_loaded = True

    @classmethod
    def schedule_of_rates(cls):
        return [
            (str(s.id()), s.Name or "Unnamed", "")
            for s in tool.Ifc.get().by_type("IfcCostSchedule")
            if s.PredefinedType == "SCHEDULEOFRATES"
        ]


class CostItemQuantitiesData:
    data = {}
    is_loaded = False

    @classmethod
    def load(cls):
        cls.data = {
            "product_quantity_names": cls.product_quantity_names(),
            "process_quantity_names": cls.process_quantity_names(),
            "resource_quantity_names": cls.resource_quantity_names(),
        }
        cls.is_loaded = True

    @classmethod
    def product_quantity_names(cls):
        total_selected_objects = len(bpy.context.selected_objects)
        names = set()
        for obj in bpy.context.selected_objects:
            element = tool.Ifc.get_entity(obj)
            if not element:
                continue
            potential_names = set()
            qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
            for qset, quantities in qtos.items():
                potential_names.update(quantities.keys())
            names = names.intersection(potential_names) if names else potential_names
        return [(n, n, "") for n in names if n != "id"]

    @classmethod
    def process_quantity_names(cls):
        active_task_index = bpy.context.scene.BIMWorkScheduleProperties.active_task_index
        total_tasks = len(bpy.context.scene.BIMTaskTreeProperties.tasks)
        if not total_tasks or active_task_index >= total_tasks:
            return []
        ifc_definition_id = bpy.context.scene.BIMTaskTreeProperties.tasks[active_task_index].ifc_definition_id
        element = tool.Ifc.get().by_id(ifc_definition_id)
        names = set()
        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        for qset, quantities in qtos.items():
            names = set(quantities.keys())
        return [(n, n, "") for n in names if n != "id"]

    @classmethod
    def resource_quantity_names(cls):
        active_resource_index = bpy.context.scene.BIMResourceProperties.active_resource_index
        total_resources = len(bpy.context.scene.BIMResourceTreeProperties.resources)
        if not total_resources or active_resource_index >= total_resources:
            return []
        ifc_definition_id = bpy.context.scene.BIMResourceTreeProperties.resources[
            active_resource_index
        ].ifc_definition_id
        element = tool.Ifc.get().by_id(ifc_definition_id)
        names = set()
        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        for qset, quantities in qtos.items():
            names = set(quantities.keys())
        return [(n, n, "") for n in names if n != "id"]
