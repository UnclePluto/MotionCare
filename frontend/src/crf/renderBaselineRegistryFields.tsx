import type {ReactNode} from "react";
import {baselineStorageToFormName} from "./baselineFormPaths";
import {CrfField} from "./components/CrfField";
import type {RegistryField} from "./types";
export function renderBaselineRegistryField(field:RegistryField): ReactNode {
 const name=baselineStorageToFormName(field.storage);
 return name ? <CrfField key={field.field_id} field={field} name={name}/> : null;
}
