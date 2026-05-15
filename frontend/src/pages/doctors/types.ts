export type DoctorGender = "male" | "female" | "unknown";

export type Doctor = {
  id: number;
  phone: string;
  name: string;
  gender: DoctorGender;
  role: string;
  date_joined: string;
  must_change_password: boolean;
  is_active: boolean;
};

export type DoctorFormValues = {
  name: string;
  gender: DoctorGender;
  phone: string;
};
