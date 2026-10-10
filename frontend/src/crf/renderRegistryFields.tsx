import type {ReactNode} from "react";
import {CrfField} from "./components/CrfField";
import {normalizeCrfFormValues} from "./formValues";
import type {RegistryField} from "./types";
import {visitRegistryStorageToFormName} from "./visitFormPaths";
export function renderVisitRegistryField(field:RegistryField,opts:{disabled?:boolean}={}):ReactNode {
 const name=visitRegistryStorageToFormName(field.storage);
 return name ? <CrfField key={field.field_id} field={field} name={name} disabled={opts.disabled}/> : null;
}
/** Keep API values intact, including historical scalars and original date precision. */
export function baselineToFormValues(raw:Record<string,unknown>):Record<string,unknown> {
 return normalizeCrfFormValues(raw);
}
